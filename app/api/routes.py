from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.models import get_all_jobs, get_job_by_id, VideoJob

router = APIRouter()


class JobResponse(BaseModel):
    id: int
    drive_file_id: str
    file_name: str
    status: str
    error: Optional[str]
    hook_text: Optional[str]
    suggested_caption: Optional[str]
    postiz_post_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/health")
def health():
    return {"status": "ok", "service": "social-media-pipeline"}


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs():
    """List all video processing jobs."""
    return get_all_jobs()


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int):
    """Get a specific job by ID."""
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, background_tasks: BackgroundTasks):
    """Retry a failed job."""
    from app.pipeline import retry_job as _retry
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("failed",):
        raise HTTPException(status_code=400, detail=f"Job status is '{job.status}', can only retry 'failed' jobs")

    background_tasks.add_task(_retry, job_id)
    return {"message": f"Job {job_id} queued for retry"}


@router.post("/trigger")
def trigger_scan(background_tasks: BackgroundTasks):
    """Manually trigger a Drive folder scan and pipeline run."""
    from app.pipeline import run_pipeline
    background_tasks.add_task(run_pipeline)
    return {"message": "Pipeline scan triggered"}
