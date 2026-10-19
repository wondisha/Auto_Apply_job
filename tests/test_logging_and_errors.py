import json
import logging

import pytest

from core import config, discovery, profile
from core.errors import (
    ApplicationRunError,
    AutoApplyError,
    ConfigurationError,
    DiscoveryError,
    DocumentGenerationError,
    PersistenceError,
    VerificationError,
    describe_error,
    exit_code_for,
)
from core.logging_config import (
    REDACTED,
    JsonFormatter,
    KeyValueFormatter,
    configure_logging,
    get_logger,
    parse_log_level,
    redact_mapping,
    redact_text,
)


def test_parse_log_level(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert parse_log_level() == logging.INFO
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert parse_log_level() == logging.DEBUG
    monkeypatch.setenv("LOG_LEVEL", "nonsense")
    assert parse_log_level() == logging.INFO
    assert parse_log_level("error") == logging.ERROR


def test_configure_logging_is_idempotent(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    logger = configure_logging()
    configure_logging()
    assert logger.level == logging.WARNING
    assert len([h for h in logger.handlers if getattr(h, "_auto_apply", False)]) == 1
    assert get_logger("core.x").name == "auto_apply.core.x"


def test_redact_text():
    text = "mail jane.doe@example.com call +1 (214) 555-0199 key AIzaSyA1234567890abcdefghijk path /home/jane/resume.pdf"
    redacted = redact_text(text)
    assert "jane.doe@example.com" not in redacted
    assert "555-0199" not in redacted
    assert "AIzaSy" not in redacted
    assert "/home/jane" not in redacted
    assert redact_text(None) is None


def test_redact_mapping_hides_sensitive_keys():
    profile_data = {"first_name": "Jane", "email": "jane@example.com", "phone": "2145550199", "GOOGLE_API_KEY": "abc"}
    redacted = redact_mapping(profile_data)
    assert redacted["first_name"] == "Jane"
    assert redacted["email"] == REDACTED
    assert redacted["phone"] == REDACTED
    assert redacted["GOOGLE_API_KEY"] == REDACTED


def _record(msg):
    return logging.LogRecord("auto_apply.test", logging.INFO, __file__, 1, msg, None, None)


def test_formatters_include_core_fields_and_redact():
    line = KeyValueFormatter().format(_record("contact jane@example.com"))
    assert "level=INFO" in line and "module=auto_apply.test" in line and "ts=" in line
    assert "jane@example.com" not in line
    payload = json.loads(JsonFormatter().format(_record("contact jane@example.com")))
    assert payload["level"] == "INFO" and payload["module"] == "auto_apply.test"
    assert "jane@example.com" not in payload["msg"]


def test_error_hierarchy_and_exit_codes():
    for cls in (ConfigurationError, DiscoveryError, VerificationError, DocumentGenerationError, ApplicationRunError, PersistenceError):
        assert issubclass(cls, AutoApplyError)
    assert issubclass(ConfigurationError, ValueError)
    assert exit_code_for(ConfigurationError("x")) == 1
    assert exit_code_for(DiscoveryError("x")) != exit_code_for(PersistenceError("x"))
    assert exit_code_for(RuntimeError("x")) == 1
    assert describe_error(DiscoveryError("none")) == "Discovery error: none"


def test_config_and_profile_raise_domain_errors(monkeypatch):
    monkeypatch.setenv("DAILY_APPLICATION_TARGET", "abc")
    with pytest.raises(ConfigurationError) as exc:
        config.get_daily_application_target()
    assert isinstance(exc.value.__cause__, ValueError)
    monkeypatch.delenv("CANDIDATE_EMAIL", raising=False)
    with pytest.raises(ConfigurationError):
        profile.validate_candidate_profile({})


def test_discovery_errors(monkeypatch):
    with pytest.raises(ConfigurationError):
        discovery.discover_job_urls("sql", "", portal="other")
    monkeypatch.setattr(discovery, "discover_linkedin_job_urls", lambda *a: [])
    with pytest.raises(DiscoveryError):
        discovery.discover_job_urls("sql", "Dallas")


def test_discovery_wraps_request_errors(monkeypatch):
    import requests

    def boom(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(discovery.requests, "get", boom)
    with pytest.raises(DiscoveryError) as exc:
        discovery.discover_linkedin_job_urls("sql", "", 5)
    assert isinstance(exc.value.__cause__, requests.ConnectionError)


def test_redact_keeps_job_ids_and_timestamps():
    text = "https://www.linkedin.com/jobs/view/3912345678901 at 2026-10-19T21:08:53Z"
    assert redact_text(text) == text


def test_configure_logging_json_format():
    logger = configure_logging(fmt="json")
    handler = next(h for h in logger.handlers if getattr(h, "_auto_apply", False))
    assert isinstance(handler.formatter, JsonFormatter)
    configure_logging(fmt="kv")
    assert isinstance(handler.formatter, KeyValueFormatter)
