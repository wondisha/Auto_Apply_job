from fastapi import APIRouter

from apply_agent import list_recent_application_events


router = APIRouter()


@router.get("")
def list_applications(limit: int = 50):
    return {"items": list_recent_application_events(limit=limit)}
