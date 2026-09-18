"""In-memory adapter implementations used for local development (`uv run
uvicorn backend.main:app`) without any GCP/HF credentials configured, i.e.
when `Settings.use_fake_adapters` is true (the default).

These are intentionally separate from the near-identical fakes under
`tests/*/fakes/` — production code (`backend.main`) must never import test
code, so a small amount of duplication here is the price of keeping that
boundary clean.
"""

from __future__ import annotations

import dataclasses
import io
from contextlib import contextmanager
from typing import BinaryIO, ContextManager

from common.models import Job, JobStatus, User
from common.ports.captcha_verifier import CaptchaResult, CaptchaVerifier
from common.ports.hf_hub_client import HFHubClient
from common.ports.hf_oauth_client import HFOAuthClient, HFOAuthUser
from common.ports.job_repository import JobRepository
from common.ports.object_storage import ObjectStorage
from common.ports.user_repository import UserRepository


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def get(self, user_id: str) -> User | None:
        user = self._users.get(user_id)
        return dataclasses.replace(user) if user else None

    def get_by_email(self, email: str) -> User | None:
        for user in self._users.values():
            if user.email == email:
                return dataclasses.replace(user)
        return None

    def get_by_hf_user_id(self, hf_user_id: str) -> User | None:
        for user in self._users.values():
            if user.hf_user_id == hf_user_id:
                return dataclasses.replace(user)
        return None

    def create(self, user: User) -> None:
        self._users[user.id] = dataclasses.replace(user)

    def update(self, user: User) -> None:
        self._users[user.id] = dataclasses.replace(user)


class InMemoryJobRepository(JobRepository):
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def get(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        return dataclasses.replace(job) if job else None

    def create(self, job: Job) -> None:
        self._jobs[job.id] = dataclasses.replace(job)

    def update(self, job: Job) -> None:
        self._jobs[job.id] = dataclasses.replace(job)

    def list_for_user(self, user_id: str) -> list[Job]:
        return [dataclasses.replace(j) for j in self._jobs.values() if j.user_id == user_id]

    def list_by_statuses(self, statuses: tuple[JobStatus, ...]) -> list[Job]:
        jobs = sorted((j for j in self._jobs.values() if j.status in statuses), key=lambda j: j.created_at)
        return [dataclasses.replace(j) for j in jobs]


class InMemoryObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def generate_upload_url(self, object_path: str, content_type: str, expires_in_seconds: int) -> str:
        return f"https://dev-local-storage/upload/{object_path}"

    def generate_download_url(self, object_path: str, expires_in_seconds: int) -> str:
        return f"https://dev-local-storage/download/{object_path}"

    def open_read_stream(self, object_path: str) -> ContextManager[BinaryIO]:
        if object_path not in self._objects:
            raise FileNotFoundError(object_path)

        @contextmanager
        def _open():
            yield io.BytesIO(self._objects[object_path])

        return _open()

    def exists(self, object_path: str) -> bool:
        return object_path in self._objects

    def delete(self, object_path: str) -> None:
        self._objects.pop(object_path, None)

    def upload_file(self, object_path: str, local_path: str) -> None:
        with open(local_path, "rb") as f:
            self._objects[object_path] = f.read()


class InMemoryHFHubClient(HFHubClient):
    def repo_exists(self, repo_id: str) -> bool:
        return False

    def list_repo_files(self, repo_id: str) -> list[str]:
        raise FileNotFoundError(repo_id)

    def get_repo_file_bytes(self, repo_id: str, path_in_repo: str) -> bytes:
        raise FileNotFoundError(f"{repo_id}:{path_in_repo}")


class InMemoryCaptchaVerifier(CaptchaVerifier):
    """Always succeeds — local dev has no reCAPTCHA site key configured."""

    def verify(self, token: str) -> CaptchaResult:
        return CaptchaResult(success=True, score=1.0)


class InMemoryHFOAuthClient(HFOAuthClient):
    def exchange_code_for_user(self, code: str, redirect_uri: str) -> HFOAuthUser:
        raise ValueError("HF OAuth is not available in local dev mode")
