from datetime import datetime, timezone

import pytest

from common.domain.job_state_machine import (
    CancelNotAllowedError,
    InvalidTransitionError,
    can_request_cancel,
    can_transition,
    request_cancel,
    transition,
)
from common.models import Job, JobStatus, PolicyType, SourceType

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_job(status: JobStatus) -> Job:
    return Job(
        id="job-1",
        user_id="user-1",
        policy=PolicyType.ACT,
        source_type=SourceType.HF_HUB,
        source_ref="some/repo",
        training_steps=1000,
        status=status,
    )


@pytest.mark.parametrize(
    "from_status,to_status,expected",
    [
        (JobStatus.QUEUED, JobStatus.INITIALIZING, True),
        (JobStatus.QUEUED, JobStatus.CANCELLED, True),
        (JobStatus.QUEUED, JobStatus.TRAINING, False),
        (JobStatus.QUEUED, JobStatus.COMPLETED, False),
        (JobStatus.INITIALIZING, JobStatus.TRAINING, True),
        (JobStatus.INITIALIZING, JobStatus.FAILED, True),
        (JobStatus.INITIALIZING, JobStatus.CANCELLED, True),
        (JobStatus.INITIALIZING, JobStatus.QUEUED, False),
        (JobStatus.TRAINING, JobStatus.COMPLETED, True),
        (JobStatus.TRAINING, JobStatus.FAILED, True),
        (JobStatus.TRAINING, JobStatus.CANCELLED, True),
        (JobStatus.COMPLETED, JobStatus.TRAINING, False),
        (JobStatus.FAILED, JobStatus.QUEUED, False),
        (JobStatus.CANCELLED, JobStatus.QUEUED, False),
    ],
)
def test_can_transition_matrix(from_status, to_status, expected):
    assert can_transition(from_status, to_status) is expected


def test_transition_returns_new_job_with_updated_status_and_timestamp():
    job = make_job(JobStatus.QUEUED)
    new_job = transition(job, JobStatus.INITIALIZING, now=NOW)

    assert new_job.status == JobStatus.INITIALIZING
    assert new_job.updated_at == NOW
    # original untouched
    assert job.status == JobStatus.QUEUED


def test_transition_raises_on_invalid_move():
    job = make_job(JobStatus.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        transition(job, JobStatus.TRAINING, now=NOW)


@pytest.mark.parametrize(
    "status,expected",
    [
        (JobStatus.QUEUED, True),
        (JobStatus.INITIALIZING, True),
        (JobStatus.TRAINING, True),
        (JobStatus.COMPLETED, False),
        (JobStatus.FAILED, False),
        (JobStatus.CANCELLED, False),
    ],
)
def test_can_request_cancel(status, expected):
    assert can_request_cancel(status) is expected


def test_request_cancel_sets_flag_when_allowed():
    job = make_job(JobStatus.TRAINING)
    cancelled = request_cancel(job, now=NOW)
    assert cancelled.cancel_requested is True
    assert cancelled.updated_at == NOW


def test_request_cancel_raises_when_terminal():
    job = make_job(JobStatus.COMPLETED)
    with pytest.raises(CancelNotAllowedError):
        request_cancel(job, now=NOW)
