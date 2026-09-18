from datetime import datetime, timedelta, timezone

from common.domain.heartbeat import is_timed_out, progress_changed, timeout_for_status
from common.models import JobStatus, Progress

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_timeout_for_status_none_for_queued_and_terminal():
    assert timeout_for_status(JobStatus.QUEUED) is None
    assert timeout_for_status(JobStatus.COMPLETED) is None
    assert timeout_for_status(JobStatus.FAILED) is None
    assert timeout_for_status(JobStatus.CANCELLED) is None


def test_initializing_times_out_after_five_minutes():
    heartbeat_at = NOW - timedelta(minutes=5, seconds=1)
    assert is_timed_out(JobStatus.INITIALIZING, heartbeat_at, NOW) is True


def test_initializing_not_timed_out_within_five_minutes():
    heartbeat_at = NOW - timedelta(minutes=4, seconds=59)
    assert is_timed_out(JobStatus.INITIALIZING, heartbeat_at, NOW) is False


def test_training_times_out_after_two_minutes_without_progress_change():
    heartbeat_at = NOW - timedelta(minutes=2, seconds=1)
    assert is_timed_out(JobStatus.TRAINING, heartbeat_at, NOW) is True


def test_training_not_timed_out_within_two_minutes():
    heartbeat_at = NOW - timedelta(minutes=1, seconds=59)
    assert is_timed_out(JobStatus.TRAINING, heartbeat_at, NOW) is False


def test_no_heartbeat_yet_is_never_timed_out():
    assert is_timed_out(JobStatus.INITIALIZING, None, NOW) is False
    assert is_timed_out(JobStatus.TRAINING, None, NOW) is False


def test_queued_never_times_out_regardless_of_heartbeat_age():
    heartbeat_at = NOW - timedelta(days=30)
    assert is_timed_out(JobStatus.QUEUED, heartbeat_at, NOW) is False


def test_progress_changed_true_when_no_previous():
    current = Progress(step=10, total_steps=1000, loss=0.5, updated_at=NOW)
    assert progress_changed(None, current) is True


def test_progress_changed_false_when_step_and_loss_identical():
    previous = Progress(step=10, total_steps=1000, loss=0.5, updated_at=NOW - timedelta(seconds=30))
    current = Progress(step=10, total_steps=1000, loss=0.5, updated_at=NOW)
    assert progress_changed(previous, current) is False


def test_progress_changed_true_when_step_advances():
    previous = Progress(step=10, total_steps=1000, loss=0.5, updated_at=NOW - timedelta(seconds=30))
    current = Progress(step=11, total_steps=1000, loss=0.49, updated_at=NOW)
    assert progress_changed(previous, current) is True
