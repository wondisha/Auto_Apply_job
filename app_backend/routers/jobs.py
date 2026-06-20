from fastapi import APIRouter, HTTPException

from apply_agent import load_job_urls, preview_ranked_jobs
from ..models import ApplyRequest, JobDiscoveryRequest


router = APIRouter()


@router.post("/discover")
def discover_jobs(payload: JobDiscoveryRequest):
    try:
        urls = load_job_urls(
            None,
            None,
            job_search_query=payload.query,
            job_search_location=payload.location,
            job_search_portal="linkedin",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"count": len(urls), "urls": urls}


@router.post("/preview")
def preview_jobs(payload: JobDiscoveryRequest):
    try:
        urls = load_job_urls(
            None,
            None,
            job_search_query=payload.query,
            job_search_location=payload.location,
            job_search_portal="linkedin",
        )
        success = preview_ranked_jobs(urls, payload.resume_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"success": success, "count": len(urls)}


@router.post("/apply")
def apply_job(payload: ApplyRequest):
    return {
        "message": "Use the CLI or Streamlit run controls for live application runs. This endpoint is a future handoff point for background jobs.",
        "job_url": payload.job_url,
    }
