from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class JobDiscoveryRequest(BaseModel):
    query: str
    location: str | None = None
    resume_path: str


class ApplyRequest(BaseModel):
    job_url: str
    resume_path: str
