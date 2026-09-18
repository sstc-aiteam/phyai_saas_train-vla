"""Heartbeat-timeout sweep, invoked by the Cloud Scheduler-triggered
internal endpoint every 5 minutes (spec section 4)."""

from __future__ import annotations

import dataclasses

from common.domain import heartbeat, job_state_machine
from common.models import Job, JobStatus, utcnow
from common.ports.job_repository import JobRepository

TIMEOUT_ERROR_MESSAGE = "Job timed out: no heartbeat update within the allowed window"

_MONITORED_STATUSES = (JobStatus.INITIALIZING, JobStatus.TRAINING)


class TimeoutService:
    def __init__(self, job_repository: JobRepository, now_fn=utcnow) -> None:
        self._jobs = job_repository
        self._now = now_fn

    def check_and_fail_timed_out_jobs(self) -> list[Job]:
        now = self._now()
        candidates = self._jobs.list_by_statuses(_MONITORED_STATUSES)

        failed_jobs = []
        for job in candidates:
            if heartbeat.is_timed_out(job.status, job.heartbeat_at, now):
                failed_job = job_state_machine.transition(job, JobStatus.FAILED, now=now)
                failed_job = dataclasses.replace(failed_job, error_message=TIMEOUT_ERROR_MESSAGE)
                self._jobs.update(failed_job)
                failed_jobs.append(failed_job)

        return failed_jobs
