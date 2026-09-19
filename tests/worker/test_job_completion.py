import json
from datetime import datetime, timezone

import pytest

from common.models import AuthProvider, Job, JobStatus, PolicyType, SourceType, User
from worker.job_completion import UPLOAD_FAILED_MESSAGE, JobCompletionMonitor

from tests.backend.fakes.fake_job_repository import FakeJobRepository
from tests.backend.fakes.fake_object_storage import FakeObjectStorage
from tests.worker.fakes.fake_docker_client import FakeDockerClient

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_job(job_id="job-1", status=JobStatus.INITIALIZING, container_id="container-1", **overrides) -> Job:
    return Job(
        id=job_id,
        user_id="user-1",
        policy=PolicyType.ACT,
        source_type=SourceType.HF_HUB,
        source_ref="org/repo",
        training_steps=1000,
        status=status,
        container_id=container_id,
        **overrides,
    )


def write_progress(output_dir, step, total_steps=1000, loss=0.1):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "progress.json").write_text(
        json.dumps({"step": step, "total_steps": total_steps, "loss": loss, "timestamp": NOW.isoformat()})
    )


def write_checkpoint(output_dir):
    checkpoint_dir = output_dir / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    (checkpoint_dir / "model.safetensors").write_bytes(b"weights")
    (checkpoint_dir / "config.json").write_text("{}")


class FlakyObjectStorage(FakeObjectStorage):
    def __init__(self, fail_times: int) -> None:
        super().__init__()
        self.fail_times = fail_times
        self.attempts = 0

    def upload_file(self, object_path: str, local_path: str) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise ConnectionError("simulated upload failure")
        super().upload_file(object_path, local_path)


@pytest.fixture
def job_repo():
    return FakeJobRepository()


@pytest.fixture
def docker():
    return FakeDockerClient()


@pytest.fixture
def storage():
    return FakeObjectStorage()


def make_monitor(job_repo, docker, storage, tmp_path, upload_retries=2):
    return JobCompletionMonitor(
        job_repo, docker, storage, workdir=str(tmp_path), upload_retries=upload_retries, now_fn=lambda: NOW
    )


def test_tick_returns_none_when_no_active_job(job_repo, docker, storage, tmp_path):
    monitor = make_monitor(job_repo, docker, storage, tmp_path)
    assert monitor.tick() is None


def test_initializing_job_gets_heartbeat_bump_while_container_alive_no_progress(job_repo, docker, storage, tmp_path):
    job_repo.create(make_job(status=JobStatus.INITIALIZING, heartbeat_at=None))
    docker.seed_running_container("container-1", _dummy_spec())
    monitor = make_monitor(job_repo, docker, storage, tmp_path)

    updated = monitor.tick()

    assert updated.status == JobStatus.INITIALIZING
    assert updated.heartbeat_at == NOW


def test_first_progress_file_advances_initializing_to_training(job_repo, docker, storage, tmp_path):
    job_repo.create(make_job(status=JobStatus.INITIALIZING))
    docker.seed_running_container("container-1", _dummy_spec())
    write_progress(tmp_path / "job-1" / "output", step=5)
    monitor = make_monitor(job_repo, docker, storage, tmp_path)

    updated = monitor.tick()

    assert updated.status == JobStatus.TRAINING
    assert updated.progress.step == 5
    assert updated.heartbeat_at == NOW


def test_training_job_records_new_progress(job_repo, docker, storage, tmp_path):
    from common.models import Progress

    job_repo.create(
        make_job(
            status=JobStatus.TRAINING,
            progress=Progress(step=5, total_steps=1000, loss=0.5, updated_at=NOW),
            heartbeat_at=NOW,
        )
    )
    docker.seed_running_container("container-1", _dummy_spec())
    write_progress(tmp_path / "job-1" / "output", step=10, loss=0.4)
    monitor = make_monitor(job_repo, docker, storage, tmp_path)

    updated = monitor.tick()

    assert updated.progress.step == 10
    assert updated.status == JobStatus.TRAINING


def test_successful_completion_uploads_checkpoint_and_cleans_up(job_repo, docker, storage, tmp_path):
    job_repo.create(make_job(status=JobStatus.TRAINING))
    output_dir = tmp_path / "job-1" / "output"
    write_progress(output_dir, step=1000)
    write_checkpoint(output_dir)
    docker.finish_container("container-1", exit_code=0)
    monitor = make_monitor(job_repo, docker, storage, tmp_path)

    updated = monitor.tick()

    assert updated.status == JobStatus.COMPLETED
    assert updated.checkpoint_gcs_path == "checkpoints/job-1.zip"
    assert storage.exists("checkpoints/job-1.zip")
    assert not (tmp_path / "job-1").exists()


def test_failed_container_exit_marks_job_failed_and_cleans_up(job_repo, docker, storage, tmp_path):
    job_repo.create(make_job(status=JobStatus.TRAINING))
    write_progress(tmp_path / "job-1" / "output", step=500)
    docker.finish_container("container-1", exit_code=1)
    monitor = make_monitor(job_repo, docker, storage, tmp_path)

    updated = monitor.tick()

    assert updated.status == JobStatus.FAILED
    assert "exited with code 1" in updated.error_message
    assert not (tmp_path / "job-1").exists()


def test_initializing_job_that_exits_before_any_progress_is_marked_failed(job_repo, docker, storage, tmp_path):
    job_repo.create(make_job(status=JobStatus.INITIALIZING))
    docker.finish_container("container-1", exit_code=1)
    monitor = make_monitor(job_repo, docker, storage, tmp_path)

    updated = monitor.tick()

    assert updated.status == JobStatus.FAILED


def test_initializing_job_that_exits_successfully_without_progress_still_completes(job_repo, docker, storage, tmp_path):
    job_repo.create(make_job(status=JobStatus.INITIALIZING))
    output_dir = tmp_path / "job-1" / "output"
    write_checkpoint(output_dir)  # produced a checkpoint despite no progress.json
    docker.finish_container("container-1", exit_code=0)
    monitor = make_monitor(job_repo, docker, storage, tmp_path)

    updated = monitor.tick()

    assert updated.status == JobStatus.COMPLETED


def test_upload_retries_then_succeeds(job_repo, docker, tmp_path):
    job_repo.create(make_job(status=JobStatus.TRAINING))
    output_dir = tmp_path / "job-1" / "output"
    write_progress(output_dir, step=1000)
    write_checkpoint(output_dir)
    docker.finish_container("container-1", exit_code=0)
    storage = FlakyObjectStorage(fail_times=2)
    monitor = make_monitor(job_repo, docker, storage, tmp_path, upload_retries=2)

    updated = monitor.tick()

    assert updated.status == JobStatus.COMPLETED
    assert storage.attempts == 3


def test_upload_fails_after_all_retries_marks_failed_and_keeps_local_checkpoint(job_repo, docker, tmp_path):
    job_repo.create(make_job(status=JobStatus.TRAINING))
    output_dir = tmp_path / "job-1" / "output"
    write_progress(output_dir, step=1000)
    write_checkpoint(output_dir)
    docker.finish_container("container-1", exit_code=0)
    storage = FlakyObjectStorage(fail_times=99)
    monitor = make_monitor(job_repo, docker, storage, tmp_path, upload_retries=2)

    updated = monitor.tick()

    assert updated.status == JobStatus.FAILED
    assert updated.error_message == UPLOAD_FAILED_MESSAGE
    assert storage.attempts == 3
    assert (tmp_path / "job-1" / "output" / "checkpoint").exists()  # kept for manual inspection


def _dummy_spec():
    from common.ports.docker_client import ContainerSpec

    return ContainerSpec(image="x", name="job-1", command=[], volumes={}, environment={}, labels={})
