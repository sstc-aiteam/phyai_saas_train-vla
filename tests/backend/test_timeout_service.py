from datetime import datetime, timedelta, timezone

import pytest

from backend.services.timeout_service import TimeoutService
from common.models import Job, JobStatus, PolicyType, SourceType

from tests.backend.fakes.fake_job_repository import FakeJobRepository

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_job(job_id: str, status: JobStatus, heartbeat_at: datetime | None) -> Job:
    return Job(
        id=job_id,
        user_id="user-1",
        policy=PolicyType.ACT,
        source_type=SourceType.HF_HUB,
        source_ref="org/repo",
        training_steps=1000,
        status=status,
        heartbeat_at=heartbeat_at,
    )


@pytest.fixture
def job_repo():
    return FakeJobRepository()


@pytest.fixture
def service(job_repo):
    return TimeoutService(job_repo, now_fn=lambda: NOW)


def test_marks_timed_out_initializing_job_as_failed(service, job_repo):
    job = make_job("job-1", JobStatus.INITIALIZING, NOW - timedelta(minutes=6))
    job_repo.create(job)

    failed = service.check_and_fail_timed_out_jobs()

    assert len(failed) == 1
    assert failed[0].status == JobStatus.FAILED
    assert job_repo.get("job-1").status == JobStatus.FAILED


def test_marks_timed_out_training_job_as_failed(service, job_repo):
    job = make_job("job-1", JobStatus.TRAINING, NOW - timedelta(minutes=3))
    job_repo.create(job)

    failed = service.check_and_fail_timed_out_jobs()

    assert len(failed) == 1
    assert failed[0].error_message is not None


def test_leaves_healthy_jobs_alone(service, job_repo):
    job = make_job("job-1", JobStatus.TRAINING, NOW - timedelta(seconds=30))
    job_repo.create(job)

    failed = service.check_and_fail_timed_out_jobs()

    assert failed == []
    assert job_repo.get("job-1").status == JobStatus.TRAINING


def test_ignores_queued_and_terminal_jobs(service, job_repo):
    job_repo.create(make_job("job-1", JobStatus.QUEUED, None))
    job_repo.create(make_job("job-2", JobStatus.COMPLETED, NOW - timedelta(days=1)))

    failed = service.check_and_fail_timed_out_jobs()

    assert failed == []


def test_no_heartbeat_yet_is_not_timed_out(service, job_repo):
    job_repo.create(make_job("job-1", JobStatus.INITIALIZING, None))

    failed = service.check_and_fail_timed_out_jobs()

    assert failed == []
