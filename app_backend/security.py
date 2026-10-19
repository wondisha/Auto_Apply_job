"""JWT issuing/verification, password hashing, user context and RBAC helpers."""
import base64
import hashlib
import hmac
import re
import secrets as pysecrets
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.errors import AuthenticationError, AuthorizationError

from .auth_config import AuthSettings, load_auth_settings

PBKDF2_ITERATIONS = 310_000
USER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$")

# Role -> permissions. Extend here when more roles are introduced.
ROLE_PERMISSIONS = {
    "user": frozenset({"profile:read", "profile:write", "applications:read", "jobs:discover"}),
    "admin": frozenset({"profile:read", "profile:write", "applications:read", "jobs:discover", "users:manage"}),
}


@dataclass(frozen=True)
class UserContext:
    user_id: str
    role: str = "user"

    @property
    def permissions(self):
        return ROLE_PERMISSIONS.get(self.role, frozenset())

    def has_permission(self, permission):
        return permission in self.permissions


def validate_user_id(user_id):
    if not isinstance(user_id, str) or not USER_ID_RE.match(user_id) or ".." in user_id:
        raise AuthenticationError("Invalid user identity.")
    return user_id


def hash_password(password, iterations=PBKDF2_ITERATIONS):
    salt = pysecrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password, stored_hash):
    try:
        scheme, iterations, salt_b64, digest_b64 = stored_hash.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def create_access_token(settings, user_id, role, now=None):
    issued_at = int(now if now is not None else time.time())
    claims = {
        "sub": validate_user_id(user_id),
        "role": role,
        "iss": settings.issuer,
        "aud": settings.audience,
        "iat": issued_at,
        "exp": issued_at + settings.access_token_ttl_seconds,
    }
    return jwt.encode(claims, settings.jwt_secret.reveal(), algorithm=settings.algorithm)


def decode_access_token(settings: AuthSettings, token):
    """Verify signature, expiry, issuer, audience and required claims; return a UserContext."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.reveal(),
            algorithms=[settings.algorithm],
            issuer=settings.issuer,
            audience=settings.audience,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid token.") from exc
    role = claims.get("role", "user")
    if not isinstance(role, str):
        raise AuthenticationError("Invalid token.")
    return UserContext(user_id=validate_user_id(claims["sub"]), role=role)


def get_auth_settings(request: Request):
    return request.app.state.auth_settings


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: AuthSettings = Depends(get_auth_settings),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Missing bearer token.")
    user = decode_access_token(settings, credentials.credentials)
    request.state.user_id = user.user_id
    return user


def require_permission(permission):
    def dependency(user: UserContext = Depends(get_current_user)):
        if not user.has_permission(permission):
            raise AuthorizationError(f"Missing required permission: {permission}")
        return user

    return dependency


def require_role(*roles):
    def dependency(user: UserContext = Depends(get_current_user)):
        if user.role not in roles:
            raise AuthorizationError("Insufficient role.")
        return user

    return dependency
