from fastapi import APIRouter, Depends

from ..models import ProfileUpdate
from ..security import UserContext, require_permission
from ..user_store import load_profile, save_profile


router = APIRouter()


@router.get("")
def get_profile(user: UserContext = Depends(require_permission("profile:read"))):
    return {"user_id": user.user_id, "profile": load_profile(user)}


@router.put("")
def put_profile(payload: ProfileUpdate, user: UserContext = Depends(require_permission("profile:write"))):
    profile = save_profile(user, payload.model_dump(exclude_none=True))
    return {"user_id": user.user_id, "profile": profile}
