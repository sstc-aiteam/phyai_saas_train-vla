from datetime import datetime, timezone

import pytest

from common.models import AuthProvider, JobStatus, PolicyType, SourceType, User
from worker.dataset_fetcher import DatasetFetcher
from worker.job_poller import JobPoller

from tests.backend.fakes.fake_hf_hub_client import FakeHFHubClient
from tests.backend.fakes.fake_job_repository import FakeJobRepository
from tests.backend.fakes.fake_object_storage import FakeObjectStorage
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
def hf_hub():
    client = FakeHFHubClient()
    client.add_repo("org/repo", {"meta/info.json": b"{}", "data/x.parquet": b"x"})
    return client


@pytest.fixture
def storage():
    return FakeObjectStorage()


@pytest.fixture
def dataset_fetcher(hf_hub, storage, tmp_path):
    return DatasetFetcher(hf_hub, storage, cache_dir=str(tmp_path / "cache"), cache_max_bytes=20 * 1024**3)


@pytest.fixture
def poller(job_repo, user_repo, docker, dataset_fetcher, tmp_path):
    return JobPoller(
        job_repo,
        user_repo,
        docker,
        dataset_fetcher,
        act_image="act-image:latest",
        smolvla_image="smolvla-image:latest",
        workdir=str(tmp_path / "jobs"),
        now_fn=lambda: NOW,
    )


def make_job(
    job_repo,
    job_id="job-1",
    user_id="user-1",
    policy=PolicyType.ACT,
    status=JobStatus.QUEUED,
    source_type=SourceType.HF_HUB,
    source_ref="org/repo",
    **kw,
):
    from common.models import Job

    job = Job(
        id=job_id,
        user_id=user_id,
        policy=policy,
        source_type=source_type,
        source_ref=source_ref,
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


def test_use_gpu_defaults_to_true(poller, job_repo, docker):
    make_job(job_repo)

    started = poller.tick()

    assert docker.get_spec(started.container_id).use_gpu is True


def test_use_gpu_can_be_disabled(job_repo, user_repo, docker, dataset_fetcher, tmp_path):
    poller = JobPoller(
        job_repo,
        user_repo,
        docker,
        dataset_fetcher,
        act_image="act-image:latest",
        smolvla_image="smolvla-image:latest",
        workdir=str(tmp_path / "jobs"),
        use_gpu=False,
        now_fn=lambda: NOW,
    )
    make_job(job_repo)

    started = poller.tick()

    assert docker.get_spec(started.container_id).use_gpu is False


def test_container_spec_mounts_input_and_output_and_passes_input_dir_flag(poller, job_repo, docker):
    make_job(job_repo)

    started = poller.tick()

    spec = docker.get_spec(started.container_id)
    assert spec.volumes[list(spec.volumes)[0]] in ("/workspace/input", "/workspace/output")
    assert set(spec.volumes.values()) == {"/workspace/input", "/workspace/output"}
    assert "--input-dir" in spec.command
    assert "/workspace/input" in spec.command


def test_hf_hub_dataset_is_mounted_read_only(poller, job_repo, docker):
    make_job(job_repo)

    started = poller.tick()

    spec = docker.get_spec(started.container_id)
    input_host_path = next(host for host, container in spec.volumes.items() if container == "/workspace/input")
    assert spec.read_only_paths == frozenset({input_host_path})


def test_tick_increments_daily_quota_when_job_enters_initializing(poller, job_repo, user_repo):
    make_job(job_repo)

    poller.tick()

    user = user_repo.get("user-1")
    assert user.daily_quota_used == 1
    assert user.quota_reset_date == NOW.date()


def test_tick_does_nothing_when_a_job_is_already_active(poller, job_repo, docker):
    make_job(job_repo, job_id="job-1", status=JobStatus.TRAINING, container_id="existing-container")
    make_job(job_repo, job_id="job-2")

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


def test_dataset_fetch_failure_marks_job_failed_but_still_consumes_quota(
    poller, job_repo, user_repo, hf_hub
):
    make_job(job_repo, source_ref="org/does-not-exist")

    result = poller.tick()

    assert result.status == JobStatus.FAILED
    assert "Failed to fetch dataset" in result.error_message
    assert result.container_id is None
    # Per spec, once a job is past `queued` (initializing/training), a
    # failure still counts toward the daily quota.
    assert user_repo.get("user-1").daily_quota_used == 1


def test_zip_upload_job_mounts_job_local_input_dir_writable(poller, job_repo, storage, docker):
    storage.put_bytes("uploads/user-1/upload-1.zip", _make_zip_bytes())
    make_job(job_repo, source_type=SourceType.ZIP_UPLOAD, source_ref="uploads/user-1/upload-1.zip")

    started = poller.tick()

    assert started.status == JobStatus.INITIALIZING
    spec = docker.get_spec(started.container_id)
    assert spec.read_only_paths == frozenset()


def _make_zip_bytes() -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("meta/info.json", "{}")
        zf.writestr("data/x.parquet", "x")
    return buf.getvalue()
