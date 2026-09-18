from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.deps import Dependencies, get_current_user_id, get_deps
from backend.services.job_service import JobView
from common.models import PolicyType, SourceType

router = APIRouter(prefix="/jobs", tags=["jobs"])


class ProgressOut(BaseModel):
    step: int
    total_steps: int
    loss: float


class JobOut(BaseModel):
    id: str
    policy: PolicyType
    source_type: SourceType
    training_steps: int
    status: str  # simplified display status, per spec 3.5 (queued/running/completed/failed/cancelled)
    queue_position: int | None
    progress: ProgressOut | None
    error_message: str | None
    created_at: datetime

    @staticmethod
    def from_view(view: JobView) -> "JobOut":
        job = view.job
        progress = None
        if job.progress is not None:
            progress = ProgressOut(step=job.progress.step, total_steps=job.progress.total_steps, loss=job.progress.loss)
        return JobOut(
            id=job.id,
            policy=job.policy,
            source_type=job.source_type,
            training_steps=job.training_steps,
            status=view.display_status,
            queue_position=view.queue_position,
            progress=progress,
            error_message=job.error_message,
            created_at=job.created_at,
        )


@router.get("", response_model=list[JobOut])
def list_my_jobs(
    deps: Dependencies = Depends(get_deps),
    user_id: str = Depends(get_current_user_id),
) -> list[JobOut]:
    views = deps.job_service.list_jobs_for_user(user_id)
    return [JobOut.from_view(v) for v in views]


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: str,
    deps: Dependencies = Depends(get_deps),
    user_id: str = Depends(get_current_user_id),
) -> JobOut:
    job = deps.job_service.request_cancel(user_id, job_id)
    views = deps.job_service.list_jobs_for_user(user_id)
    view = next(v for v in views if v.job.id == job.id)
    return JobOut.from_view(view)


class DownloadUrlOut(BaseModel):
    url: str


@router.get("/{job_id}/download-url", response_model=DownloadUrlOut)
def get_download_url(
    job_id: str,
    deps: Dependencies = Depends(get_deps),
    user_id: str = Depends(get_current_user_id),
) -> DownloadUrlOut:
    url = deps.job_service.get_download_url(user_id, job_id, deps.storage)
    return DownloadUrlOut(url=url)
