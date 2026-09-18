from datetime import datetime, timezone

import pytest

from common.models import AuthProvider, JobStatus, PolicyType, SourceType, User
from worker.job_poller import JobPoller

from tests.backend.fakes.fake_job_repository import FakeJobRepository
from tests.backend.fakes.fake_user_repository import FakeUserRepository
from tests.worker.fakes.fake_docker_client import FakeDockerClient

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def job_repo():
    return FakeJobRepository()


@pytest.fixture
def user_repo():
    repo = FakeUserRepository()
    repo.create(User(id="user-1", auth_provider=AuthProvider.EMAIL, email="a@example.com"))
    return repo


@pytest.fixture
def docker():
    return FakeDockerClient()


@pytest.fixture
def poller(job_repo, user_repo, docker):
    return JobPoller(
        job_repo,
        user_repo,
        docker,
        act_image="act-image:latest",
        smolvla_image="smolvla-image:latest",
        workdir="/data/jobs",
        now_fn=lambda: NOW,
    )


def make_job(job_repo, job_id="job-1", user_id="user-1", policy=PolicyType.ACT, status=JobStatus.QUEUED, **kw):
    from common.models import Job

    job = Job(
        id=job_id,
        user_id=user_id,
        policy=policy,
        source_type=SourceType.HF_HUB,
        source_ref="org/repo",
        training_steps=1000,
        status=status,
        **kw,
    )
    job_repo.create(job)
    return job


def test_tick_starts_the_oldest_queued_job(poller, job_repo, docker):
    make_job(job_repo)

    started = poller.tick()

    assert started.status == JobStatus.INITIALIZING
    assert started.container_id is not None
    assert job_repo.get("job-1").status == JobStatus.INITIALIZING
    assert docker.is_running(started.container_id)


def test_tick_uses_the_right_image_per_policy(poller, job_repo, docker):
    make_job(job_repo, policy=PolicyType.SMOLVLA)

    started = poller.tick()

    spec = docker.get_spec(started.container_id)
    assert spec.image == "smolvla-image:latest"


def test_tick_increments_daily_quota_when_container_starts(poller, job_repo, user_repo):
    make_job(job_repo)

    poller.tick()

    user = user_repo.get("user-1")
    assert user.daily_quota_used == 1
    assert user.quota_reset_date == NOW.date()


def test_tick_does_nothing_when_a_job_is_already_active(poller, job_repo, docker):
    make_job(job_repo, job_id="job-1", status=JobStatus.TRAINING, container_id="existing-container")
    make_job(job_repo, job_id="job-2", status=JobStatus.QUEUED)

    started = poller.tick()

    assert started is None
    assert job_repo.get("job-2").status == JobStatus.QUEUED


def test_tick_returns_none_when_queue_is_empty(poller):
    assert poller.tick() is None


def test_tick_processes_cancellation_before_starting_new_jobs(poller, job_repo, user_repo):
    make_job(job_repo, job_id="job-1", cancel_requested=True)
    make_job(job_repo, job_id="job-2")

    started = poller.tick()

    assert job_repo.get("job-1").status == JobStatus.CANCELLED
    assert started.id == "job-2"
    # job-1 never started a container, so it must not consume daily quota.
    assert user_repo.get("user-1").daily_quota_used == 1
