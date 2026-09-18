"""Port: persistence for Job documents (implemented by Firestore adapter / fakes)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from common.models import Job, JobStatus


class JobRepository(ABC):
    @abstractmethod
    def get(self, job_id: str) -> Job | None: ...

    @abstractmethod
    def create(self, job: Job) -> None: ...

    @abstractmethod
    def update(self, job: Job) -> None: ...

    @abstractmethod
    def list_for_user(self, user_id: str) -> list[Job]: ...

    @abstractmethod
    def list_by_statuses(self, statuses: tuple[JobStatus, ...]) -> list[Job]:
        """Return jobs in any of the given statuses, oldest first."""
        ...
