"""Centralized logging setup and sensitive-data redaction helpers."""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

ROOT_LOGGER_NAME = "auto_apply"
DEFAULT_LOG_LEVEL = "INFO"
REDACTED = "[REDACTED]"

SENSITIVE_KEY_MARKERS = (
    "email",
    "phone",
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "authorization",
    "jwt",
    "credential",
    "cookie",
    "linkedin_url",
    "github_url",
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<![\w/])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?!\w)")
_API_KEY_RE = re.compile(r"\b(?:AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{16,})\b")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
_HOME_PATH_RE = re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\Users\\)[^/\\\s]+")


def parse_log_level(value=None):
    """Parse a log level name (e.g. 'debug'); invalid or empty values fall back to INFO."""
    if value is None:
        value = os.getenv("LOG_LEVEL", "")
    name = str(value).strip().upper() or DEFAULT_LOG_LEVEL
    level = logging.getLevelName(name)
    return level if isinstance(level, int) else logging.INFO


def redact_text(text):
    """Mask emails, phone numbers, API keys and user home directories in free text."""
    if text is None:
        return text
    text = str(text)
    text = _BEARER_RE.sub(REDACTED, text)
    text = _JWT_RE.sub(REDACTED, text)
    text = _API_KEY_RE.sub(REDACTED, text)
    text = _EMAIL_RE.sub(REDACTED, text)
    text = _PHONE_RE.sub(REDACTED, text)
    return _HOME_PATH_RE.sub("~", text)


def is_sensitive_key(key):
    lowered = str(key).lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_MARKERS)


def redact_mapping(mapping):
    """Return a copy with sensitive keys masked and string values scrubbed."""
    result = {}
    for key, value in (mapping or {}).items():
        if is_sensitive_key(key):
            result[key] = REDACTED if value else value
        elif isinstance(value, dict):
            result[key] = redact_mapping(value)
        elif isinstance(value, str):
            result[key] = redact_text(value)
        else:
            result[key] = value
    return result


class KeyValueFormatter(logging.Formatter):
    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        message = json.dumps(redact_text(record.getMessage()))
        line = f"ts={timestamp} level={record.levelname} module={record.name} msg={message}"
        if record.exc_info:
            line += " exc=" + json.dumps(redact_text(self.formatException(record.exc_info)))
        return line


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "module": record.name,
            "msg": redact_text(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload)


def configure_logging(level=None, fmt=None):
    """Configure the shared 'auto_apply' logger. Safe to call repeatedly."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(parse_log_level(level))
    fmt = (fmt or os.getenv("LOG_FORMAT", "kv")).strip().lower()
    formatter = JsonFormatter() if fmt == "json" else KeyValueFormatter()
    handler = next((h for h in logger.handlers if getattr(h, "_auto_apply", False)), None)
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler._auto_apply = True
        logger.addHandler(handler)
        logger.propagate = False
    handler.setFormatter(formatter)
    return logger


def get_logger(name=None):
    """Return a child logger of the shared 'auto_apply' logger."""
    full_name = ROOT_LOGGER_NAME if not name else f"{ROOT_LOGGER_NAME}.{name.removeprefix(ROOT_LOGGER_NAME + '.')}"
    return logging.getLogger(full_name)
