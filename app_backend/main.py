from fastapi import FastAPI

from .routers import applications, auth, jobs


app = FastAPI(title="Auto Apply Job API", version="0.1.0")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(applications.router, prefix="/applications", tags=["applications"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])


@app.get("/health")
def health_check():
    return {"status": "ok"}
