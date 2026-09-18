"""Heartbeat updates for jobs the worker is actively monitoring (spec
section 4). Called once per poll tick for the currently-running job."""

from __future__ import annotations

import dataclasses

from common.domain import heartbeat
from common.models import Job, Progress, utcnow
from common.ports.job_repository import JobRepository


class HeartbeatUpdater:
    def __init__(self, job_repository: JobRepository, now_fn=utcnow) -> None:
        self._jobs = job_repository
        self._now = now_fn

    def mark_container_alive(self, job: Job) -> Job:
        """`initializing` phase: bump the heartbeat as long as the container
        process is alive, regardless of training progress."""
        updated = dataclasses.replace(job, heartbeat_at=self._now())
        self._jobs.update(updated)
        return updated

    def record_progress(self, job: Job, latest_progress: Progress) -> Job:
        """`training` phase: only bump the heartbeat (and store the new
        progress) when progress.json content actually changed."""
        if not heartbeat.progress_changed(job.progress, latest_progress):
            return job
        updated = dataclasses.replace(job, progress=latest_progress, heartbeat_at=self._now())
        self._jobs.update(updated)
        return updated
