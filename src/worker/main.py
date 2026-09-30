"""Worker process entrypoint (spec section 2), meant to be run under
systemd with `Restart=always`.

Startup sequence: acquire the single-flight lock, sweep stale `.tmp`
download dirs, reconcile against any containers left running from a
previous worker process, then poll forever. Each tick: `JobPoller` fetches
the next queued job's dataset (into the shared HF cache, or by extracting
its uploaded zip) and starts its container; `JobCompletionMonitor` tracks
the currently-active job's progress and, once its container exits,
packages/uploads the checkpoint (spec 3.7).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from common.models import JobStatus
from worker.config import WorkerSettings
from worker.deps import WorkerDependencies, build_default_worker_dependencies
from worker.disk_manager import cleanup_stale_tmp_dirs
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
        deps = build_default_worker_dependencies(settings)
        run_forever(settings, deps)
    finally:
        lock.release()


def run_forever(settings: WorkerSettings, deps: WorkerDependencies) -> None:
    """The worker's poll loop, factored out from `main()` so a manual-test
    harness can build its own `WorkerDependencies` (sharing adapter
    instances with a backend process) and drive this same loop without
    going through `main()`'s real-Firestore/GCS wiring or its own lock."""
    for stale_dir in cleanup_stale_tmp_dirs(Path(settings.hf_cache_dir), settings.tmp_stale_after_seconds):
        logger.info("Removed stale tmp download dir: %s", stale_dir)

    reconciliation = reconcile(deps.docker_client, deps.job_repository)
    logger.info(
        "Startup reconciliation: resumed=%s killed_orphans=%s",
        [job.id for job in reconciliation.resumed_jobs],
        reconciliation.killed_orphan_container_ids,
    )

    logger.info("Worker started, polling every %.1fs", settings.poll_interval_seconds)
    while True:
        tick(deps)
        time.sleep(settings.poll_interval_seconds)


def tick(deps: WorkerDependencies) -> None:
    started_job = deps.poller.tick()
    if started_job is not None:
        logger.info("Started job %s (container=%s)", started_job.id, started_job.container_id)

    monitored_job = deps.completion_monitor.tick()
    if monitored_job is not None and monitored_job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        logger.info(
            "Job %s finished: status=%s error=%s",
            monitored_job.id,
            monitored_job.status.value,
            monitored_job.error_message,
        )


if __name__ == "__main__":
    main()
