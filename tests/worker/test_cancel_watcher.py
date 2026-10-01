from datetime import datetime, timezone

import pytest

from common.models import Job, JobStatus, PolicyType, SourceType
from common.ports.docker_client import ContainerSpec
from worker.cancel_watcher import process_cancellations

from tests.backend.fakes.fake_job_repository import FakeJobRepository
from tests.worker.fakes.fake_docker_client import FakeDockerClient

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_job(job_id: str, status: JobStatus, cancel_requested: bool, container_id: str | None = None) -> Job:
    return Job(
        id=job_id,
        user_id="user-1",
        policy=PolicyType.ACT,
        source_type=SourceType.HF_HUB,
        source_ref="org/repo",
        training_steps=1000,
        status=status,
        cancel_requested=cancel_requested,
        container_id=container_id,
    )


@pytest.fixture
def job_repo():
    return FakeJobRepository()


@pytest.fixture
def docker():
    return FakeDockerClient()


def test_queued_cancel_moves_to_cancelled_without_touching_docker(job_repo, docker, tmp_path):
    job_repo.create(make_job("job-1", JobStatus.QUEUED, cancel_requested=True))

    cancelled = process_cancellations(job_repo, docker, str(tmp_path), now_fn=lambda: NOW)

    assert [j.id for j in cancelled] == ["job-1"]
    assert job_repo.get("job-1").status == JobStatus.CANCELLED
    assert docker.killed == []


def test_training_cancel_kills_container_then_cancels(job_repo, docker, tmp_path):
    docker.seed_running_container(
        "container-1",
        ContainerSpec(image="x", name="job-1", command=[], volumes={}, environment={}, labels={}),
    )
    job_repo.create(make_job("job-1", JobStatus.TRAINING, cancel_requested=True, container_id="container-1"))

    cancelled = process_cancellations(job_repo, docker, str(tmp_path), now_fn=lambda: NOW)

    assert [j.id for j in cancelled] == ["job-1"]
    assert job_repo.get("job-1").status == JobStatus.CANCELLED
    assert docker.killed == ["container-1"]


def test_training_cancel_removes_job_working_directory(job_repo, docker, tmp_path):
    docker.seed_running_container(
        "container-1",
        ContainerSpec(image="x", name="job-1", command=[], volumes={}, environment={}, labels={}),
    )
    job_repo.create(make_job("job-1", JobStatus.TRAINING, cancel_requested=True, container_id="container-1"))
    job_dir = tmp_path / "job-1"
    (job_dir / "input").mkdir(parents=True)
    (job_dir / "input" / "dataset.bin").write_bytes(b"fake dataset bytes")

    process_cancellations(job_repo, docker, str(tmp_path), now_fn=lambda: NOW)

    assert not job_dir.exists()


def test_queued_cancel_does_not_touch_any_directory(job_repo, docker, tmp_path):
    # A queued job never had a job dir created for it yet (dataset fetching
    # only starts once a job moves to `initializing`), so cancelling it must
    # not assume one exists or error out because it doesn't.
    job_repo.create(make_job("job-1", JobStatus.QUEUED, cancel_requested=True))

    process_cancellations(job_repo, docker, str(tmp_path), now_fn=lambda: NOW)

    assert list(tmp_path.iterdir()) == []


def test_jobs_without_cancel_requested_are_left_alone(job_repo, docker, tmp_path):
    job_repo.create(make_job("job-1", JobStatus.TRAINING, cancel_requested=False, container_id="container-1"))

    cancelled = process_cancellations(job_repo, docker, str(tmp_path), now_fn=lambda: NOW)

    assert cancelled == []
    assert job_repo.get("job-1").status == JobStatus.TRAINING


def test_terminal_jobs_are_not_scanned(job_repo, docker, tmp_path):
    job = make_job("job-1", JobStatus.COMPLETED, cancel_requested=True)
    job_repo.create(job)

    cancelled = process_cancellations(job_repo, docker, str(tmp_path), now_fn=lambda: NOW)

    assert cancelled == []
