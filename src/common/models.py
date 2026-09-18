"""Domain models shared by the backend API and the training worker.

These are plain data holders with no I/O — they are safe to import from
pure domain logic, service layers, and tests alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    QUEUED = "queued"
    INITIALIZING = "initializing"
    TRAINING = "training"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Statuses in which a job occupies a "concurrent job" slot for its owner.
ACTIVE_STATUSES = (JobStatus.QUEUED, JobStatus.INITIALIZING, JobStatus.TRAINING)

# Statuses in which a training container has been started (or was started)
# on the GPU host. Used to decide whether a job counts toward daily quota.
CONTAINER_STARTED_STATUSES = (
    JobStatus.INITIALIZING,
    JobStatus.TRAINING,
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
)

TERMINAL_STATUSES = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


class PolicyType(str, Enum):
    ACT = "act"
    SMOLVLA = "smolvla"


class SourceType(str, Enum):
    HF_HUB = "hf_hub"
    ZIP_UPLOAD = "zip_upload"


class AuthProvider(str, Enum):
    EMAIL = "email"
    HUGGINGFACE = "huggingface"


@dataclass
class User:
    id: str
    auth_provider: AuthProvider
    email: str | None = None
    password_hash: str | None = None
    hf_user_id: str | None = None
    daily_quota_used: int = 0
    quota_reset_date: date | None = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class Progress:
    step: int
    total_steps: int
    loss: float
    updated_at: datetime


@dataclass
class Job:
    id: str
    user_id: str
    policy: PolicyType
    source_type: SourceType
    source_ref: str
    training_steps: int
    status: JobStatus = JobStatus.QUEUED
    container_id: str | None = None
    heartbeat_at: datetime | None = None
    progress: Progress | None = None
    cancel_requested: bool = False
    checkpoint_gcs_path: str | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
