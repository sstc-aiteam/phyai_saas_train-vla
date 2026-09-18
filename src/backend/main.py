from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.api import auth, internal, jobs, uploads
from backend.config import Settings, get_settings
from backend.deps import Dependencies, build_dependencies
from backend.security.jwt_tokens import InvalidTokenError
from backend.services.auth_service import (
    CaptchaFailedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)
from backend.services.job_service import (
    DownloadNotAvailableError,
    InvalidTrainingStepsError,
    JobNotFoundError,
    NotJobOwnerError,
    QuotaExceededError,
    UserNotFoundError,
)
from backend.services.upload_service import (
    HFDatasetNotFoundError,
    UploadNotFoundError,
    UploadValidationError,
)

# Maps domain/service exceptions to HTTP status codes. Kept as one table so
# every use case gets consistent error handling without each endpoint
# needing its own try/except.
_EXCEPTION_STATUS_CODES: dict[type[Exception], int] = {
    CaptchaFailedError: 400,
    EmailAlreadyRegisteredError: 409,
    InvalidCredentialsError: 401,
    InvalidTokenError: 401,
    UserNotFoundError: 404,
    JobNotFoundError: 404,
    NotJobOwnerError: 403,
    QuotaExceededError: 429,
    InvalidTrainingStepsError: 400,
    DownloadNotAvailableError: 409,
    UploadValidationError: 400,
    UploadNotFoundError: 404,
    HFDatasetNotFoundError: 404,
}


def _build_default_dependencies(settings: Settings) -> Dependencies:
    if settings.use_fake_adapters:
        from backend.adapters.memory import (
            InMemoryCaptchaVerifier,
            InMemoryHFHubClient,
            InMemoryHFOAuthClient,
            InMemoryJobRepository,
            InMemoryObjectStorage,
            InMemoryUserRepository,
        )

        return build_dependencies(
            settings,
            user_repository=InMemoryUserRepository(),
            job_repository=InMemoryJobRepository(),
            storage=InMemoryObjectStorage(),
            hf_hub_client=InMemoryHFHubClient(),
            captcha_verifier=InMemoryCaptchaVerifier(),
            hf_oauth_client=InMemoryHFOAuthClient(),
        )

    from google.cloud import firestore, storage

    from backend.adapters.firestore.job_repository import FirestoreJobRepository
    from backend.adapters.firestore.user_repository import FirestoreUserRepository
    from backend.adapters.gcs.object_storage import GCSObjectStorage
    from backend.adapters.hf.hf_hub_client import RealHFHubClient
    from backend.adapters.hf.hf_oauth_client import RealHFOAuthClient
    from backend.adapters.recaptcha.verifier import GoogleRecaptchaVerifier

    firestore_client = firestore.Client()
    return build_dependencies(
        settings,
        user_repository=FirestoreUserRepository(firestore_client),
        job_repository=FirestoreJobRepository(firestore_client),
        storage=GCSObjectStorage(storage.Client(), settings.gcs_bucket),
        hf_hub_client=RealHFHubClient(),
        captcha_verifier=GoogleRecaptchaVerifier(settings.recaptcha_secret_key),
        hf_oauth_client=RealHFOAuthClient(settings.hf_oauth_client_id, settings.hf_oauth_client_secret),
    )


def build_app(settings: Settings | None = None, deps: Dependencies | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="LeRobot Training Service")
    app.state.deps = deps or _build_default_dependencies(settings)

    app.include_router(auth.router)
    app.include_router(uploads.router)
    app.include_router(jobs.router)
    app.include_router(internal.router)

    for exc_type, status_code in _EXCEPTION_STATUS_CODES.items():
        app.add_exception_handler(
            exc_type,
            lambda request, exc, status_code=status_code: JSONResponse(
                status_code=status_code, content={"detail": str(exc)}
            ),
        )

    return app


app = build_app()
