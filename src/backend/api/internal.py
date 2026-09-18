"""Endpoint invoked by Cloud Scheduler every 5 minutes (spec section 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.deps import Dependencies, get_deps, verify_scheduler_secret

router = APIRouter(prefix="/internal", tags=["internal"])


class CheckTimeoutsOut(BaseModel):
    failed_job_ids: list[str]


@router.post("/check-timeouts", response_model=CheckTimeoutsOut, dependencies=[Depends(verify_scheduler_secret)])
def check_timeouts(deps: Dependencies = Depends(get_deps)) -> CheckTimeoutsOut:
    failed_jobs = deps.timeout_service.check_and_fail_timed_out_jobs()
    return CheckTimeoutsOut(failed_job_ids=[job.id for job in failed_jobs])
