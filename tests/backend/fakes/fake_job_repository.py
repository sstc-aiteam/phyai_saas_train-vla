from __future__ import annotations

import dataclasses

from common.models import Job, JobStatus
from common.ports.job_repository import JobRepository


class FakeJobRepository(JobRepository):
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def get(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        return dataclasses.replace(job) if job else None

    def create(self, job: Job) -> None:
        if job.id in self._jobs:
            raise ValueError(f"Job {job.id} already exists")
        self._jobs[job.id] = dataclasses.replace(job)

    def update(self, job: Job) -> None:
        if job.id not in self._jobs:
            raise KeyError(f"Job {job.id} does not exist")
        self._jobs[job.id] = dataclasses.replace(job)

    def list_for_user(self, user_id: str) -> list[Job]:
        return [dataclasses.replace(j) for j in self._jobs.values() if j.user_id == user_id]

    def list_by_statuses(self, statuses: tuple[JobStatus, ...]) -> list[Job]:
        jobs = [j for j in self._jobs.values() if j.status in statuses]
        jobs.sort(key=lambda j: j.created_at)
        return [dataclasses.replace(j) for j in jobs]
