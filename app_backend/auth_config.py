"""Auth configuration loaded from environment variables and validated up front."""
import os
from dataclasses import dataclass, field

from core.errors import ConfigurationError

from .secrets_provider import Secret, get_secret_provider

ALLOWED_ALGORITHMS = ("HS256", "HS384", "HS512")
MIN_SECRET_LENGTH = 32
PLACEHOLDER_MARKERS = ("<", ">")


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: Secret = field(repr=False)
    issuer: str
    audience: str
    algorithm: str
    access_token_ttl_seconds: int
    login_username: str
    login_password_hash: Secret = field(repr=False)
    login_role: str


def _required(name):
    value = os.getenv(name, "").strip()
    if not value or any(marker in value for marker in PLACEHOLDER_MARKERS):
        return None
    return value


def load_auth_settings():
    """Build AuthSettings, raising one ConfigurationError that lists every problem."""
    problems = []
    provider = get_secret_provider()

    secret = provider.get("AUTH_JWT_SECRET")
    if not secret or any(marker in secret for marker in PLACEHOLDER_MARKERS):
        problems.append("AUTH_JWT_SECRET is required")
        secret = None
    elif len(secret) < MIN_SECRET_LENGTH:
        problems.append(f"AUTH_JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters")

    issuer = _required("AUTH_JWT_ISSUER")
    audience = _required("AUTH_JWT_AUDIENCE")
    username = _required("AUTH_LOGIN_USERNAME")
    password_hash = provider.get("AUTH_LOGIN_PASSWORD_HASH")
    for name, value in (("AUTH_JWT_ISSUER", issuer), ("AUTH_JWT_AUDIENCE", audience), ("AUTH_LOGIN_USERNAME", username)):
        if not value:
            problems.append(f"{name} is required")
    if not password_hash or any(marker in password_hash for marker in PLACEHOLDER_MARKERS):
        problems.append("AUTH_LOGIN_PASSWORD_HASH is required (generate with: python -m app_backend.security_cli)")
        password_hash = None

    algorithm = os.getenv("AUTH_JWT_ALGORITHM", "HS256").strip().upper()
    if algorithm not in ALLOWED_ALGORITHMS:
        problems.append(f"AUTH_JWT_ALGORITHM must be one of {', '.join(ALLOWED_ALGORITHMS)}")

    ttl_raw = os.getenv("AUTH_ACCESS_TOKEN_TTL_SECONDS", "3600").strip()
    try:
        ttl = int(ttl_raw)
        if ttl <= 0:
            raise ValueError
    except ValueError:
        problems.append("AUTH_ACCESS_TOKEN_TTL_SECONDS must be a positive integer")
        ttl = 0

    role = os.getenv("AUTH_LOGIN_ROLE", "user").strip().lower() or "user"

    if problems:
        raise ConfigurationError(
            "Invalid backend auth configuration: " + "; ".join(problems) + ". See app_backend/README.md."
        )
    return AuthSettings(
        jwt_secret=Secret(secret),
        issuer=issuer,
        audience=audience,
        algorithm=algorithm,
        access_token_ttl_seconds=ttl,
        login_username=username,
        login_password_hash=Secret(password_hash),
        login_role=role,
    )
