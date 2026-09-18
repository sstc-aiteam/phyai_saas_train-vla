"""Worker process entrypoint (spec section 2), meant to be run under
systemd with `Restart=always`.

Startup sequence: acquire the single-flight lock, sweep stale `.tmp`
download dirs, reconcile against any containers left running from a
previous worker process, then poll forever.

NOTE: this loop currently covers queueing, starting, and cancelling jobs
(`JobPoller`) plus startup reconciliation — it does not yet poll
`progress.json` for the currently-running container, detect container exit,
or package/upload the finished checkpoint. Those pieces need the actual
per-policy training container to exist first; see `docker/*/Dockerfile`.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from google.cloud import firestore

from backend.adapters.firestore.job_repository import FirestoreJobRepository
from backend.adapters.firestore.user_repository import FirestoreUserRepository
from worker.config import WorkerSettings
from worker.disk_manager import cleanup_stale_tmp_dirs
from worker.docker_runner import DockerRunner
from worker.job_poller import JobPoller
from worker.lock import LockAcquisitionError, WorkerLock
from worker.orphan_reconciler import reconcile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lerobot.worker")


def main() -> None:
    settings = WorkerSettings()

    lock = WorkerLock(settings.lock_file_path)
    try:
        lock.acquire()
    except LockAcquisitionError:
        logger.error("Another worker process already holds the lock at %s", settings.lock_file_path)
        raise SystemExit(1)

    try:
        _run(settings)
    finally:
        lock.release()


def _run(settings: WorkerSettings) -> None:
    firestore_client = firestore.Client()
    job_repository = FirestoreJobRepository(firestore_client)
    user_repository = FirestoreUserRepository(firestore_client)
    docker_client = DockerRunner()

    for stale_dir in cleanup_stale_tmp_dirs(Path(settings.hf_cache_dir), settings.tmp_stale_after_seconds):
        logger.info("Removed stale tmp download dir: %s", stale_dir)

    reconciliation = reconcile(docker_client, job_repository)
    logger.info(
        "Startup reconciliation: resumed=%s killed_orphans=%s",
        [job.id for job in reconciliation.resumed_jobs],
        reconciliation.killed_orphan_container_ids,
    )

    poller = JobPoller(
        job_repository,
        user_repository,
        docker_client,
        act_image=settings.act_image,
        smolvla_image=settings.smolvla_image,
        workdir=settings.workdir,
    )

    logger.info("Worker started, polling every %.1fs", settings.poll_interval_seconds)
    while True:
        started_job = poller.tick()
        if started_job is not None:
            logger.info("Started job %s (container=%s)", started_job.id, started_job.container_id)
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
