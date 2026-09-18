"""Dependency wiring: builds services from either fake (in-memory) or real
adapters depending on Settings, and exposes FastAPI `Depends`-compatible
accessors. Kept separate from `main.py` so tests can call `build_dependencies`
directly with overrides instead of spinning up the whole app."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request

from backend.config import Settings
from backend.security.jwt_tokens import InvalidTokenError, decode_access_token
from backend.services.auth_service import AuthService
from backend.services.job_service import JobService
from backend.services.timeout_service import TimeoutService
from backend.services.upload_service import UploadService
from common.ports.captcha_verifier import CaptchaVerifier
from common.ports.hf_hub_client import HFHubClient
from common.ports.hf_oauth_client import HFOAuthClient
from common.ports.job_repository import JobRepository
from common.ports.object_storage import ObjectStorage
from common.ports.user_repository import UserRepository


@dataclass
class Dependencies:
    settings: Settings
    user_repository: UserRepository
    job_repository: JobRepository
    storage: ObjectStorage
    auth_service: AuthService
    job_service: JobService
    upload_service: UploadService
    timeout_service: TimeoutService


def build_dependencies(
    settings: Settings,
    user_repository: UserRepository,
    job_repository: JobRepository,
    storage: ObjectStorage,
    hf_hub_client: HFHubClient,
    captcha_verifier: CaptchaVerifier,
    hf_oauth_client: HFOAuthClient,
) -> Dependencies:
    job_service = JobService(job_repository, user_repository)
    return Dependencies(
        settings=settings,
        user_repository=user_repository,
        job_repository=job_repository,
        storage=storage,
        auth_service=AuthService(
            user_repository, captcha_verifier, hf_oauth_client, min_captcha_score=settings.min_captcha_score
        ),
        job_service=job_service,
        upload_service=UploadService(storage, hf_hub_client, job_service),
        timeout_service=TimeoutService(job_repository),
    )


def get_deps(request: Request) -> Dependencies:
    return request.app.state.deps


def get_current_user_id(
    deps: Dependencies = Depends(get_deps),
    authorization: str | None = Header(default=None),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return decode_access_token(token, deps.settings.jwt_secret)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def verify_scheduler_secret(
    deps: Dependencies = Depends(get_deps),
    x_scheduler_secret: str | None = Header(default=None),
) -> None:
    if x_scheduler_secret != deps.settings.scheduler_shared_secret:
        raise HTTPException(status_code=401, detail="Invalid scheduler secret")
