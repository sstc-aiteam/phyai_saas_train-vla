"""Cancellation handling (spec section 3.6).

Scans queued/initializing/training jobs for `cancel_requested`:
- still `queued` (container never started) -> move straight to `cancelled`,
  nothing to kill, and this never consumed daily quota.
- `initializing`/`training` (container is running) -> `docker kill` it, then
  move to `cancelled`. Any partial checkpoint is discarded by the caller
  (job_poller.py never uploads a checkpoint for a cancelled job).
"""

from __future__ import annotations

from common.domain import job_state_machine
from common.models import Job, JobStatus, utcnow
from common.ports.docker_client import DockerClient
from common.ports.job_repository import JobRepository

_CANCELLABLE_STATUSES = (JobStatus.QUEUED, JobStatus.INITIALIZING, JobStatus.TRAINING)


def process_cancellations(
    job_repository: JobRepository, docker_client: DockerClient, now_fn=utcnow
) -> list[Job]:
    now = now_fn()
    candidates = job_repository.list_by_statuses(_CANCELLABLE_STATUSES)

    cancelled_jobs = []
    for job in candidates:
        if not job.cancel_requested:
            continue

        if job.status in (JobStatus.INITIALIZING, JobStatus.TRAINING) and job.container_id:
            docker_client.kill(job.container_id)

        updated = job_state_machine.transition(job, JobStatus.CANCELLED, now=now)
        job_repository.update(updated)
        cancelled_jobs.append(updated)

    return cancelled_jobs
