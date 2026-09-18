"""Per-user quota rules.

- At most MAX_CONCURRENT_JOBS jobs in an active status (queued/initializing/
  training) at any time.
- At most MAX_DAILY_JOBS jobs per UTC calendar day where the training
  container actually started. A job cancelled while still `queued` (the
  container was never started) does NOT count toward the daily quota; a job
  cancelled or failed after `initializing` DOES count.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date

from common.models import ACTIVE_STATUSES, Job, User

MAX_CONCURRENT_JOBS = 1
MAX_DAILY_JOBS = 10


def count_active(jobs: list[Job]) -> int:
    return sum(1 for job in jobs if job.status in ACTIVE_STATUSES)


def has_free_concurrent_slot(jobs: list[Job], max_concurrent: int = MAX_CONCURRENT_JOBS) -> bool:
    return count_active(jobs) < max_concurrent


def effective_daily_used(user: User, today: date) -> int:
    """Daily counter, implicitly reset to 0 once `today` rolls past quota_reset_date."""
    if user.quota_reset_date != today:
        return 0
    return user.daily_quota_used


def has_daily_quota_remaining(user: User, today: date, max_daily: int = MAX_DAILY_JOBS) -> bool:
    return effective_daily_used(user, today) < max_daily


@dataclass(frozen=True)
class QuotaCheckResult:
    allowed: bool
    reason: str | None = None


def can_create_job(user: User, active_jobs: list[Job], today: date) -> QuotaCheckResult:
    if not has_free_concurrent_slot(active_jobs):
        return QuotaCheckResult(False, "You already have a job queued or in progress.")
    if not has_daily_quota_remaining(user, today):
        return QuotaCheckResult(False, "Daily job quota exceeded.")
    return QuotaCheckResult(True)


def record_job_started(user: User, today: date) -> User:
    """Increment the daily counter. Call exactly once, when a job transitions
    from `queued` to `initializing` (i.e. its container actually starts)."""
    used = effective_daily_used(user, today)
    return dataclasses.replace(user, daily_quota_used=used + 1, quota_reset_date=today)
