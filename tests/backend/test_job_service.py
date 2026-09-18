import dataclasses
from datetime import datetime, timezone

import pytest

from backend.services.job_service import (
    DownloadNotAvailableError,
    InvalidTrainingStepsError,
    JobService,
    NotJobOwnerError,
    QuotaExceededError,
    UserNotFoundError,
)
from common.domain import job_state_machine
from common.models import AuthProvider, JobStatus, PolicyType, SourceType, User

from tests.backend.fakes.fake_job_repository import FakeJobRepository
from tests.backend.fakes.fake_object_storage import FakeObjectStorage
from tests.backend.fakes.fake_user_repository import FakeUserRepository

FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def user_repo():
    repo = FakeUserRepository()
    repo.create(User(id="user-1", auth_provider=AuthProvider.EMAIL, email="a@example.com"))
    return repo


@pytest.fixture
def job_repo():
    return FakeJobRepository()


@pytest.fixture
def service(job_repo, user_repo):
    return JobService(job_repo, user_repo, now_fn=lambda: FIXED_NOW)


def test_create_job_succeeds(service):
    job = service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/dataset", 1000)
    assert job.status == JobStatus.QUEUED
    assert job.user_id == "user-1"


def test_create_job_rejects_invalid_training_steps(service):
    with pytest.raises(InvalidTrainingStepsError):
        service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/dataset", 0)


def test_create_job_rejects_unknown_user(service):
    with pytest.raises(UserNotFoundError):
        service.create_job("no-such-user", PolicyType.ACT, SourceType.HF_HUB, "org/dataset", 1000)


def test_create_job_blocked_while_another_job_is_active(service):
    service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/dataset", 1000)
    with pytest.raises(QuotaExceededError):
        service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/dataset2", 1000)


def test_create_job_blocked_when_daily_quota_exhausted(service, user_repo):
    user = user_repo.get("user-1")
    user.daily_quota_used = 10
    user.quota_reset_date = FIXED_NOW.date()
    user_repo.update(user)

    with pytest.raises(QuotaExceededError):
        service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/dataset", 1000)


def test_list_jobs_for_user_reports_queue_position(service, job_repo):
    job_a = service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/a", 1000)
    # request_cancel only sets the flag (see job_state_machine); a queued job
    # that never started its container is actually moved to CANCELLED by the
    # worker's poll loop the next time it looks at the queue (see
    # worker/job_poller.py) — simulate that step here to free the slot.
    cancel_requested = service.request_cancel("user-1", job_a.id)
    job_repo.update(job_state_machine.transition(cancel_requested, JobStatus.CANCELLED, now=FIXED_NOW))

    job_b = service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/b", 1000)

    views = service.list_jobs_for_user("user-1")
    by_id = {v.job.id: v for v in views}
    assert by_id[job_b.id].queue_position == 1
    assert by_id[job_a.id].queue_position is None
    assert by_id[job_a.id].display_status == "cancelled"


def test_list_jobs_collapses_initializing_and_training_to_running(service, job_repo):
    job = service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/a", 1000)
    initializing = job_state_machine.transition(job, JobStatus.INITIALIZING, now=FIXED_NOW)
    job_repo.update(initializing)

    views = service.list_jobs_for_user("user-1")
    assert views[0].display_status == "running"


def test_request_cancel_from_queued_succeeds(service):
    job = service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/a", 1000)
    cancelled = service.request_cancel("user-1", job.id)
    assert cancelled.cancel_requested is True


def test_request_cancel_rejects_non_owner(service):
    job = service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/a", 1000)
    with pytest.raises(NotJobOwnerError):
        service.request_cancel("someone-else", job.id)


def test_download_url_requires_completed_job_with_checkpoint(service, job_repo):
    job = service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/a", 1000)
    storage = FakeObjectStorage()
    with pytest.raises(DownloadNotAvailableError):
        service.get_download_url("user-1", job.id, storage)


def test_download_url_succeeds_when_completed(service, job_repo):
    job = service.create_job("user-1", PolicyType.ACT, SourceType.HF_HUB, "org/a", 1000)
    initializing = job_state_machine.transition(job, JobStatus.INITIALIZING, now=FIXED_NOW)
    training = job_state_machine.transition(initializing, JobStatus.TRAINING, now=FIXED_NOW)
    completed = job_state_machine.transition(training, JobStatus.COMPLETED, now=FIXED_NOW)
    completed = dataclasses.replace(completed, checkpoint_gcs_path="checkpoints/job-1.zip")
    job_repo.update(completed)

    storage = FakeObjectStorage()
    url = service.get_download_url("user-1", job.id, storage)
    assert "checkpoints/job-1.zip" in url
