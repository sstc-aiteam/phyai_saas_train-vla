from datetime import datetime, timezone

import pytest

from common.models import Job, JobStatus, PolicyType, SourceType
from common.ports.docker_client import ContainerSpec
from worker.orphan_reconciler import reconcile

from tests.backend.fakes.fake_job_repository import FakeJobRepository
from tests.worker.fakes.fake_docker_client import FakeDockerClient

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_job(job_id: str, status: JobStatus, container_id: str | None) -> Job:
    return Job(
        id=job_id,
        user_id="user-1",
        policy=PolicyType.ACT,
        source_type=SourceType.HF_HUB,
        source_ref="org/repo",
        training_steps=1000,
        status=status,
        container_id=container_id,
    )


def make_spec(name: str) -> ContainerSpec:
    return ContainerSpec(
        image="lerobot-train-act:latest",
        name=name,
        command=["python", "train_entrypoint.py"],
        volumes={},
        environment={},
        labels={},
    )


@pytest.fixture
def job_repo():
    return FakeJobRepository()


@pytest.fixture
def docker():
    return FakeDockerClient()


def test_matching_container_is_resumed_not_killed(job_repo, docker):
    job_repo.create(make_job("job-1", JobStatus.TRAINING, "container-1"))
    docker.seed_running_container("container-1", make_spec("job-1"))

    result = reconcile(docker, job_repo)

    assert [j.id for j in result.resumed_jobs] == ["job-1"]
    assert result.killed_orphan_container_ids == []
    assert docker.is_running("container-1") is True


def test_orphan_container_is_killed(job_repo, docker):
    docker.seed_running_container("orphan-container", make_spec("mystery"))

    result = reconcile(docker, job_repo)

    assert result.resumed_jobs == []
    assert result.killed_orphan_container_ids == ["orphan-container"]
    assert docker.is_running("orphan-container") is False


def test_mixed_case_resumes_matching_and_kills_orphan(job_repo, docker):
    job_repo.create(make_job("job-1", JobStatus.INITIALIZING, "container-1"))
    docker.seed_running_container("container-1", make_spec("job-1"))
    docker.seed_running_container("container-2", make_spec("orphan"))

    result = reconcile(docker, job_repo)

    assert [j.id for j in result.resumed_jobs] == ["job-1"]
    assert result.killed_orphan_container_ids == ["container-2"]


def test_no_running_containers_is_a_noop(job_repo, docker):
    job_repo.create(make_job("job-1", JobStatus.TRAINING, "container-1"))

    result = reconcile(docker, job_repo)

    assert result.resumed_jobs == []
    assert result.killed_orphan_container_ids == []


def test_at_most_one_container_ever_ends_up_running(job_repo, docker):
    job_repo.create(make_job("job-1", JobStatus.TRAINING, "container-1"))
    docker.seed_running_container("container-1", make_spec("job-1"))
    docker.seed_running_container("container-2", make_spec("leftover"))
    docker.seed_running_container("container-3", make_spec("leftover-2"))

    reconcile(docker, job_repo)

    assert docker.list_running_container_ids() == ["container-1"]
