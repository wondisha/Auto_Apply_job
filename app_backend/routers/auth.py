import hmac

from fastapi import APIRouter, Depends, HTTPException

from core.errors import AuthenticationError
from core.logging_config import get_logger

from ..auth_config import AuthSettings
from ..models import LoginRequest
from ..security import UserContext, create_access_token, get_auth_settings, get_current_user, verify_password


router = APIRouter()
logger = get_logger("backend.auth")

# Verified against when the username is unknown so response timing does not reveal valid usernames.
_DUMMY_HASH = "pbkdf2_sha256$310000$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@router.post("/login")
def login(payload: LoginRequest, settings: AuthSettings = Depends(get_auth_settings)):
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required.")
    username_ok = hmac.compare_digest(payload.username.encode(), settings.login_username.encode())
    stored_hash = settings.login_password_hash.reveal() if username_ok else _DUMMY_HASH
    password_ok = verify_password(payload.password, stored_hash)
    if not (username_ok and password_ok):
        logger.warning("Login failed")
        raise AuthenticationError("Invalid username or password.")
    token = create_access_token(settings, settings.login_username, settings.login_role)
    logger.info("Login succeeded for user_id=%s", settings.login_username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_seconds,
    }


@router.get("/me")
def me(user: UserContext = Depends(get_current_user)):
    return {"user_id": user.user_id, "role": user.role, "permissions": sorted(user.permissions)}
