"""Job status state machine.

    queued -> initializing -> training -> completed
                            \\-> failed          \\-> failed
    queued/initializing/training -> cancelled (via cancel_requested)

Pure functions only — no I/O, no clock reads except via an injected `now`.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from common.models import ACTIVE_STATUSES, Job, JobStatus

_ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.INITIALIZING, JobStatus.CANCELLED}),
    JobStatus.INITIALIZING: frozenset({JobStatus.TRAINING, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.TRAINING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


class InvalidTransitionError(Exception):
    def __init__(self, from_status: JobStatus, to_status: JobStatus):
        super().__init__(f"Cannot transition job from {from_status.value!r} to {to_status.value!r}")
        self.from_status = from_status
        self.to_status = to_status


def can_transition(from_status: JobStatus, to_status: JobStatus) -> bool:
    return to_status in _ALLOWED_TRANSITIONS[from_status]


def transition(job: Job, to_status: JobStatus, *, now: datetime) -> Job:
    """Return a new Job with `status` moved to `to_status`.

    Raises InvalidTransitionError if the move is not allowed from the job's
    current status.
    """
    if not can_transition(job.status, to_status):
        raise InvalidTransitionError(job.status, to_status)
    return dataclasses.replace(job, status=to_status, updated_at=now)


def can_request_cancel(status: JobStatus) -> bool:
    return status in ACTIVE_STATUSES


class CancelNotAllowedError(Exception):
    def __init__(self, status: JobStatus):
        super().__init__(f"Cannot cancel a job in status {status.value!r}")
        self.status = status


def request_cancel(job: Job, *, now: datetime) -> Job:
    if not can_request_cancel(job.status):
        raise CancelNotAllowedError(job.status)
    return dataclasses.replace(job, cancel_requested=True, updated_at=now)
