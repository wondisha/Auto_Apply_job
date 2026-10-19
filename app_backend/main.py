from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.errors import AuthenticationError, AuthorizationError, AutoApplyError, ConfigurationError
from core.logging_config import configure_logging, get_logger

from .auth_config import load_auth_settings
from .routers import applications, auth, jobs, profile


logger = get_logger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Fail fast with an actionable error if auth/secrets env vars are missing or invalid.
    app.state.auth_settings = load_auth_settings()
    yield


app = FastAPI(title="Auto Apply Job API", version="0.2.0", lifespan=lifespan)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(profile.router, prefix="/profile", tags=["profile"])
app.include_router(applications.router, prefix="/applications", tags=["applications"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])


@app.exception_handler(AutoApplyError)
async def domain_error_handler(request: Request, exc: AutoApplyError):
    headers = None
    if isinstance(exc, AuthenticationError):
        status = 401
        headers = {"WWW-Authenticate": "Bearer"}
    elif isinstance(exc, AuthorizationError):
        status = 403
    elif isinstance(exc, ConfigurationError):
        status = 400
    else:
        status = 500
    if status >= 500:
        logger.error("Unhandled domain error: %s", exc)
    detail = str(exc) if status < 500 else "Internal server error."
    return JSONResponse(status_code=status, content={"detail": detail, "category": exc.category}, headers=headers)


@app.get("/health")
def health_check():
    return {"status": "ok"}
