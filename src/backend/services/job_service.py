"""Job lifecycle use cases: creation (with quota check), listing for the
polling "My Jobs" page, cancellation, and checkpoint download links."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from common.domain import job_state_machine, limits, quota
from common.models import (
    Job,
    JobStatus,
    PolicyType,
    SourceType,
    utcnow,
)
from common.ports.job_repository import JobRepository
from common.ports.object_storage import ObjectStorage
from common.ports.user_repository import UserRepository

DOWNLOAD_URL_EXPIRES_IN_SECONDS = 7 * 24 * 60 * 60  # 7 days, per spec


class UserNotFoundError(Exception):
    pass


class JobNotFoundError(Exception):
    pass


class NotJobOwnerError(Exception):
    pass


class QuotaExceededError(Exception):
    pass


class InvalidTrainingStepsError(Exception):
    pass


class DownloadNotAvailableError(Exception):
    pass


# The internal status is simplified for end users per spec section 3.5:
# `initializing`/`training` are both shown as "preparing / training", and
# no other internal sub-state is exposed.
_DISPLAY_STATUS = {
    JobStatus.QUEUED: "queued",
    JobStatus.INITIALIZING: "running",
    JobStatus.TRAINING: "running",
    JobStatus.COMPLETED: "completed",
    JobStatus.FAILED: "failed",
    JobStatus.CANCELLED: "cancelled",
}


@dataclass(frozen=True)
class JobView:
    job: Job
    display_status: str
    queue_position: int | None  # 1-based position among queued jobs, else None


class JobService:
    def __init__(
        self,
        job_repository: JobRepository,
        user_repository: UserRepository,
        now_fn=utcnow,
    ) -> None:
        self._jobs = job_repository
        self._users = user_repository
        self._now = now_fn

    def create_job(
        self,
        user_id: str,
        policy: PolicyType,
        source_type: SourceType,
        source_ref: str,
        training_steps: int,
    ) -> Job:
        steps_result = limits.validate_training_steps(training_steps)
        if not steps_result.ok:
            raise InvalidTrainingStepsError(steps_result.error)

        user = self._users.get(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        active_jobs = self._jobs.list_for_user(user_id)
        today = self._now().date()
        quota_result = quota.can_create_job(user, active_jobs, today)
        if not quota_result.allowed:
            raise QuotaExceededError(quota_result.reason)

        now = self._now()
        job = Job(
            id=str(uuid.uuid4()),
            user_id=user_id,
            policy=policy,
            source_type=source_type,
            source_ref=source_ref,
            training_steps=training_steps,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        self._jobs.create(job)
        return job

    def get_job(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def list_jobs_for_user(self, user_id: str) -> list[JobView]:
        jobs = self._jobs.list_for_user(user_id)
        queued_ids_in_order = [j.id for j in self._jobs.list_by_statuses((JobStatus.QUEUED,))]

        views = []
        for job in jobs:
            queue_position = None
            if job.status == JobStatus.QUEUED:
                queue_position = queued_ids_in_order.index(job.id) + 1
            views.append(JobView(job=job, display_status=_DISPLAY_STATUS[job.status], queue_position=queue_position))
        return views

    def request_cancel(self, user_id: str, job_id: str) -> Job:
        job = self.get_job(job_id)
        if job.user_id != user_id:
            raise NotJobOwnerError(job_id)

        updated = job_state_machine.request_cancel(job, now=self._now())
        self._jobs.update(updated)
        return updated

    def get_download_url(self, user_id: str, job_id: str, storage: ObjectStorage) -> str:
        job = self.get_job(job_id)
        if job.user_id != user_id:
            raise NotJobOwnerError(job_id)
        if job.status != JobStatus.COMPLETED or not job.checkpoint_gcs_path:
            raise DownloadNotAvailableError(job_id)
        return storage.generate_download_url(job.checkpoint_gcs_path, DOWNLOAD_URL_EXPIRES_IN_SECONDS)
