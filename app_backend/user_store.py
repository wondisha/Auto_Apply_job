"""Per-user profile storage. Every path is derived from the authenticated user_id."""
import json
import os
from pathlib import Path

from core.errors import AuthorizationError, ConfigurationError, PersistenceError

from .security import UserContext, validate_user_id

DEFAULT_USER_DATA_DIR = ".user_data"
PROFILE_FIELDS = (
    "first_name", "last_name", "email", "phone", "linkedin_url", "github_url", "location", "sponsorship_needed",
)


def get_user_data_root():
    return Path(os.getenv("USER_DATA_DIR", DEFAULT_USER_DATA_DIR)).resolve()


def assert_same_user(user: UserContext, target_user_id):
    """Guardrail: callers may only act on their own data."""
    if user.user_id != target_user_id:
        raise AuthorizationError("Cross-user access is not allowed.")


def user_dir(user_id):
    validate_user_id(user_id)
    root = get_user_data_root()
    path = (root / user_id).resolve()
    if root not in path.parents:
        raise AuthorizationError("Invalid user data path.")
    return path


def load_profile(user: UserContext, target_user_id=None):
    assert_same_user(user, target_user_id or user.user_id)
    path = user_dir(user.user_id) / "profile.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PersistenceError(f"Could not read profile: {exc}") from exc


def save_profile(user: UserContext, profile, target_user_id=None):
    assert_same_user(user, target_user_id or user.user_id)
    unknown = sorted(set(profile) - set(PROFILE_FIELDS))
    if unknown:
        raise ConfigurationError(f"Unknown profile fields: {', '.join(unknown)}")
    clean = {key: str(value) for key, value in profile.items()}
    directory = user_dir(user.user_id)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "profile.json").write_text(json.dumps(clean), encoding="utf-8")
    except OSError as exc:
        raise PersistenceError(f"Could not write profile: {exc}") from exc
    return clean
