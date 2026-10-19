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


class ProfileUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    location: str | None = None
    sponsorship_needed: str | None = None
