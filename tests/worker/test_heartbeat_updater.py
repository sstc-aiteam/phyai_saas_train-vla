from datetime import datetime, timedelta, timezone

import pytest

from common.models import JobStatus, PolicyType, Progress, SourceType, Job
from worker.heartbeat_updater import HeartbeatUpdater

from tests.backend.fakes.fake_job_repository import FakeJobRepository

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=1)


def make_job(**overrides) -> Job:
    defaults = dict(
        id="job-1",
        user_id="user-1",
        policy=PolicyType.ACT,
        source_type=SourceType.HF_HUB,
        source_ref="org/repo",
        training_steps=1000,
        status=JobStatus.INITIALIZING,
    )
    defaults.update(overrides)
    return Job(**defaults)


@pytest.fixture
def job_repo():
    return FakeJobRepository()


def test_mark_container_alive_bumps_heartbeat(job_repo):
    job_repo.create(make_job(heartbeat_at=T0))
    updater = HeartbeatUpdater(job_repo, now_fn=lambda: T1)

    updated = updater.mark_container_alive(job_repo.get("job-1"))

    assert updated.heartbeat_at == T1
    assert job_repo.get("job-1").heartbeat_at == T1


def test_record_progress_bumps_heartbeat_when_step_advances(job_repo):
    initial_progress = Progress(step=10, total_steps=1000, loss=0.5, updated_at=T0)
    job_repo.create(make_job(status=JobStatus.TRAINING, heartbeat_at=T0, progress=initial_progress))
    updater = HeartbeatUpdater(job_repo, now_fn=lambda: T1)

    new_progress = Progress(step=11, total_steps=1000, loss=0.49, updated_at=T1)
    updated = updater.record_progress(job_repo.get("job-1"), new_progress)

    assert updated.progress == new_progress
    assert updated.heartbeat_at == T1


def test_record_progress_does_not_bump_heartbeat_when_unchanged(job_repo):
    initial_progress = Progress(step=10, total_steps=1000, loss=0.5, updated_at=T0)
    job_repo.create(make_job(status=JobStatus.TRAINING, heartbeat_at=T0, progress=initial_progress))
    updater = HeartbeatUpdater(job_repo, now_fn=lambda: T1)

    same_progress = Progress(step=10, total_steps=1000, loss=0.5, updated_at=T1)
    updated = updater.record_progress(job_repo.get("job-1"), same_progress)

    assert updated.heartbeat_at == T0
    assert job_repo.get("job-1").heartbeat_at == T0
