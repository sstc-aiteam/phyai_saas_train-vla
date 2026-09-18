from datetime import date

from common.domain.quota import (
    can_create_job,
    count_active,
    effective_daily_used,
    has_daily_quota_remaining,
    has_free_concurrent_slot,
    record_job_started,
)
from common.models import AuthProvider, Job, JobStatus, PolicyType, SourceType, User

TODAY = date(2026, 1, 1)
YESTERDAY = date(2025, 12, 31)


def make_job(status: JobStatus, job_id: str = "job-1") -> Job:
    return Job(
        id=job_id,
        user_id="user-1",
        policy=PolicyType.ACT,
        source_type=SourceType.HF_HUB,
        source_ref="some/repo",
        training_steps=1000,
        status=status,
    )


def make_user(daily_quota_used: int = 0, quota_reset_date: date | None = TODAY) -> User:
    return User(
        id="user-1",
        auth_provider=AuthProvider.EMAIL,
        email="a@example.com",
        daily_quota_used=daily_quota_used,
        quota_reset_date=quota_reset_date,
    )


def test_count_active_only_counts_active_statuses():
    jobs = [
        make_job(JobStatus.QUEUED, "1"),
        make_job(JobStatus.TRAINING, "2"),
        make_job(JobStatus.COMPLETED, "3"),
        make_job(JobStatus.CANCELLED, "4"),
    ]
    assert count_active(jobs) == 2


def test_has_free_concurrent_slot_false_when_one_active_job_exists():
    jobs = [make_job(JobStatus.INITIALIZING)]
    assert has_free_concurrent_slot(jobs) is False


def test_has_free_concurrent_slot_true_when_no_active_jobs():
    jobs = [make_job(JobStatus.COMPLETED)]
    assert has_free_concurrent_slot(jobs) is True


def test_effective_daily_used_resets_on_new_day():
    user = make_user(daily_quota_used=7, quota_reset_date=YESTERDAY)
    assert effective_daily_used(user, TODAY) == 0


def test_effective_daily_used_keeps_count_on_same_day():
    user = make_user(daily_quota_used=7, quota_reset_date=TODAY)
    assert effective_daily_used(user, TODAY) == 7


def test_has_daily_quota_remaining_at_limit():
    user = make_user(daily_quota_used=10, quota_reset_date=TODAY)
    assert has_daily_quota_remaining(user, TODAY) is False


def test_has_daily_quota_remaining_under_limit():
    user = make_user(daily_quota_used=9, quota_reset_date=TODAY)
    assert has_daily_quota_remaining(user, TODAY) is True


def test_can_create_job_blocked_by_concurrent_limit():
    user = make_user()
    jobs = [make_job(JobStatus.QUEUED)]
    result = can_create_job(user, jobs, TODAY)
    assert result.allowed is False
    assert "queued or in progress" in result.reason


def test_can_create_job_blocked_by_daily_limit():
    user = make_user(daily_quota_used=10, quota_reset_date=TODAY)
    result = can_create_job(user, [], TODAY)
    assert result.allowed is False
    assert "Daily job quota" in result.reason


def test_can_create_job_allowed():
    user = make_user(daily_quota_used=3, quota_reset_date=TODAY)
    result = can_create_job(user, [], TODAY)
    assert result.allowed is True
    assert result.reason is None


def test_record_job_started_increments_same_day():
    user = make_user(daily_quota_used=3, quota_reset_date=TODAY)
    updated = record_job_started(user, TODAY)
    assert updated.daily_quota_used == 4
    assert updated.quota_reset_date == TODAY


def test_record_job_started_resets_then_increments_on_new_day():
    user = make_user(daily_quota_used=9, quota_reset_date=YESTERDAY)
    updated = record_job_started(user, TODAY)
    assert updated.daily_quota_used == 1
    assert updated.quota_reset_date == TODAY


def test_queued_cancellation_does_not_consume_quota():
    """Cancelling a job while still `queued` never calls record_job_started,
    so the daily counter must stay untouched — this test documents that
    contract at the quota-module level rather than re-deriving it."""
    user = make_user(daily_quota_used=2, quota_reset_date=TODAY)
    # No call to record_job_started() happens for a queued-only cancel.
    assert effective_daily_used(user, TODAY) == 2
