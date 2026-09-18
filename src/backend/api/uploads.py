from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.jobs import JobOut
from backend.deps import Dependencies, get_current_user_id, get_deps
from common.domain.limits import MAX_TRAINING_STEPS
from common.models import PolicyType

router = APIRouter(prefix="/uploads", tags=["uploads"])


class UploadTargetOut(BaseModel):
    upload_id: str
    upload_url: str


@router.post("/zip/target", response_model=UploadTargetOut)
def create_zip_upload_target(
    deps: Dependencies = Depends(get_deps),
    user_id: str = Depends(get_current_user_id),
) -> UploadTargetOut:
    upload_id, url = deps.upload_service.create_upload_target(user_id)
    return UploadTargetOut(upload_id=upload_id, upload_url=url)


class ConfirmZipUploadRequest(BaseModel):
    upload_id: str
    policy: PolicyType
    training_steps: int = Field(gt=0, le=MAX_TRAINING_STEPS)


def _job_out_for(deps: Dependencies, user_id: str, job_id: str) -> JobOut:
    views = deps.job_service.list_jobs_for_user(user_id)
    view = next(v for v in views if v.job.id == job_id)
    return JobOut.from_view(view)


@router.post("/zip/confirm", response_model=JobOut)
def confirm_zip_upload(
    body: ConfirmZipUploadRequest,
    deps: Dependencies = Depends(get_deps),
    user_id: str = Depends(get_current_user_id),
) -> JobOut:
    job = deps.upload_service.confirm_zip_upload(user_id, body.upload_id, body.policy, body.training_steps)
    return _job_out_for(deps, user_id, job.id)


class SubmitHFDatasetRequest(BaseModel):
    repo_id: str
    policy: PolicyType
    training_steps: int = Field(gt=0, le=MAX_TRAINING_STEPS)


@router.post("/hf-dataset", response_model=JobOut)
def submit_hf_dataset(
    body: SubmitHFDatasetRequest,
    deps: Dependencies = Depends(get_deps),
    user_id: str = Depends(get_current_user_id),
) -> JobOut:
    job = deps.upload_service.submit_hf_dataset(user_id, body.repo_id, body.policy, body.training_steps)
    return _job_out_for(deps, user_id, job.id)
