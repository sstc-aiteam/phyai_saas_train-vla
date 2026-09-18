"""Worker-restart reconciliation (spec section 4).

On startup, compare containers actually running on the host against the
jobs Firestore thinks are `initializing`/`training`:

- container id matches a tracked job -> resume monitoring it (nothing to
  do here beyond reporting it; the poller picks it back up)
- container is running but doesn't match any tracked job -> orphan, kill it

This guarantees at most one training container ever occupies the GPU.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.models import Job, JobStatus
from common.ports.docker_client import DockerClient
from common.ports.job_repository import JobRepository

_MONITORED_STATUSES = (JobStatus.INITIALIZING, JobStatus.TRAINING)


@dataclass(frozen=True)
class ReconciliationResult:
    resumed_jobs: list[Job]
    killed_orphan_container_ids: list[str]


def reconcile(docker_client: DockerClient, job_repository: JobRepository) -> ReconciliationResult:
    running_container_ids = set(docker_client.list_running_container_ids())
    tracked_jobs = job_repository.list_by_statuses(_MONITORED_STATUSES)
    tracked_container_ids = {job.container_id for job in tracked_jobs if job.container_id}

    resumed_jobs = [job for job in tracked_jobs if job.container_id in running_container_ids]

    orphan_ids = running_container_ids - tracked_container_ids
    for container_id in orphan_ids:
        docker_client.kill(container_id)

    return ReconciliationResult(resumed_jobs=resumed_jobs, killed_orphan_container_ids=sorted(orphan_ids))
