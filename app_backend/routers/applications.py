from fastapi import APIRouter, Depends

from apply_agent import list_recent_application_events

from ..security import UserContext, require_permission


router = APIRouter()


@router.get("")
def list_applications(limit: int = 50, user: UserContext = Depends(require_permission("applications:read"))):
    limit = max(1, min(limit, 200))
    return {"items": list_recent_application_events(limit=limit, user_id=user.user_id)}
