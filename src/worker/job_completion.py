"""Monitors the single currently-active (`initializing`/`training`) job:
reads its `progress.json`, advances `initializing` -> `training` on the
first progress update, and — once its container exits — packages and
uploads the checkpoint (or marks the job `failed`) per spec section 3.7.

Runs alongside `JobPoller` in the worker's poll loop: `JobPoller.tick()`
starts new jobs when none is active, this monitors the one that is.
"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

from common.domain import job_state_machine
from common.models import Job, JobStatus, utcnow
from common.ports.docker_client import DockerClient
from common.ports.job_repository import JobRepository
from common.ports.object_storage import ObjectStorage

from worker.checkpoint_packager import package_checkpoint
from worker.heartbeat_updater import HeartbeatUpdater
from worker.progress_reader import read_progress

_MONITORED_STATUSES = (JobStatus.INITIALIZING, JobStatus.TRAINING)

UPLOAD_FAILED_MESSAGE = "Training completed but checkpoint upload failed; please resubmit the job."


class JobCompletionMonitor:
    def __init__(
        self,
        job_repository: JobRepository,
        docker_client: DockerClient,
        storage: ObjectStorage,
        workdir: str,
        upload_retries: int = 2,
        now_fn=utcnow,
    ) -> None:
        self._jobs = job_repository
        self._docker = docker_client
        self._storage = storage
        self._workdir = Path(workdir)
        self._upload_retries = upload_retries
        self._now = now_fn
        self._heartbeat = HeartbeatUpdater(job_repository, now_fn=now_fn)

    def tick(self) -> Job | None:
        active_jobs = self._jobs.list_by_statuses(_MONITORED_STATUSES)
        if not active_jobs:
            return None
        job = active_jobs[0]  # JobPoller guarantees at most one at a time

        progress = read_progress(self._output_dir(job))
        exit_code = self._docker.get_exit_code(job.container_id) if job.container_id else None

        if progress is not None:
            if job.status == JobStatus.INITIALIZING:
                job = job_state_machine.transition(job, JobStatus.TRAINING, now=self._now())
                self._jobs.update(job)
            job = self._heartbeat.record_progress(job, progress)
        elif job.status == JobStatus.INITIALIZING and exit_code is None:
            job = self._heartbeat.mark_container_alive(job)

        if exit_code is None:
            return job  # container still running, nothing more to do this tick

        return self._finalize(job, exit_code)

    def _finalize(self, job: Job, exit_code: int) -> Job:
        if job.status == JobStatus.INITIALIZING:
            # Container exited before writing any progress.json (e.g. it
            # crashed instantly). Move through `training` first so the
            # terminal transition below stays within the normal state
            # machine (only `training` -> completed/failed is allowed).
            job = job_state_machine.transition(job, JobStatus.TRAINING, now=self._now())
            self._jobs.update(job)

        if exit_code != 0:
            return self._mark_failed(job, f"Training container exited with code {exit_code}", cleanup=True)

        checkpoint_dir = self._checkpoint_dir(job)
        zip_path = self._output_dir(job) / "checkpoint.zip"
        try:
            package_checkpoint(checkpoint_dir, zip_path)
        except Exception as exc:
            return self._mark_failed(job, f"Failed to package checkpoint: {exc}", cleanup=True)

        object_path = f"checkpoints/{job.id}.zip"
        if self._upload_with_retries(object_path, zip_path):
            return self._mark_completed(job, object_path)

        # Per spec: keep the local checkpoint for manual inspection instead
        # of cleaning up the job dir.
        return self._mark_failed(job, UPLOAD_FAILED_MESSAGE, cleanup=False)

    def _upload_with_retries(self, object_path: str, local_zip_path: Path) -> bool:
        attempts = 1 + self._upload_retries
        for _ in range(attempts):
            try:
                self._storage.upload_file(object_path, str(local_zip_path))
                return True
            except Exception:
                continue
        return False

    def _mark_completed(self, job: Job, checkpoint_gcs_path: str) -> Job:
        completed = job_state_machine.transition(job, JobStatus.COMPLETED, now=self._now())
        completed = dataclasses.replace(completed, checkpoint_gcs_path=checkpoint_gcs_path)
        self._jobs.update(completed)
        self._cleanup_job_dir(job)
        return completed

    def _mark_failed(self, job: Job, error_message: str, *, cleanup: bool) -> Job:
        failed = job_state_machine.transition(job, JobStatus.FAILED, now=self._now())
        failed = dataclasses.replace(failed, error_message=error_message)
        self._jobs.update(failed)
        if cleanup:
            self._cleanup_job_dir(job)
        return failed

    def _job_dir(self, job: Job) -> Path:
        return self._workdir / job.id

    def _output_dir(self, job: Job) -> Path:
        return self._job_dir(job) / "output"

    def _checkpoint_dir(self, job: Job) -> Path:
        return self._output_dir(job) / "checkpoint"

    def _cleanup_job_dir(self, job: Job) -> None:
        shutil.rmtree(self._job_dir(job), ignore_errors=True)
