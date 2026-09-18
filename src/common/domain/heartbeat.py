"""Heartbeat / timeout rules.

- `initializing`: the worker updates the heartbeat as long as the container
  process is alive, regardless of training progress. Timeout: 5 minutes
  with no heartbeat update at all.
- `training`: the worker only updates the heartbeat when `progress.json`
  content (step/loss) actually changes. Timeout: 2 minutes with no change.
- `queued` and terminal statuses have no heartbeat timeout.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from common.models import JobStatus, Progress

INITIALIZING_TIMEOUT = timedelta(minutes=5)
TRAINING_TIMEOUT = timedelta(minutes=2)

_TIMEOUTS: dict[JobStatus, timedelta] = {
    JobStatus.INITIALIZING: INITIALIZING_TIMEOUT,
    JobStatus.TRAINING: TRAINING_TIMEOUT,
}


def timeout_for_status(status: JobStatus) -> timedelta | None:
    return _TIMEOUTS.get(status)


def is_timed_out(status: JobStatus, heartbeat_at: datetime | None, now: datetime) -> bool:
    """Whether a job stuck in `status` should be treated as timed out.

    A job that has no heartbeat_at yet is never timed out here — the caller
    is responsible for seeding heartbeat_at when a job enters a status that
    has a timeout.
    """
    threshold = timeout_for_status(status)
    if threshold is None or heartbeat_at is None:
        return False
    return (now - heartbeat_at) > threshold


def progress_changed(previous: Progress | None, current: Progress) -> bool:
    """Whether new progress.json content differs from the last-seen progress,
    per the rule that `training` heartbeats only advance on real change."""
    if previous is None:
        return True
    return (previous.step, previous.loss) != (current.step, current.loss)
