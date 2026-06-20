from fastapi import APIRouter, HTTPException

from ..models import LoginRequest


router = APIRouter()


@router.post("/login")
def login(payload: LoginRequest):
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required.")
    return {
        "message": "Placeholder login endpoint. Replace with real auth before production use.",
        "user": payload.username,
    }
