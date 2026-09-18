from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.deps import build_dependencies
from backend.main import build_app

from tests.backend.fakes.fake_captcha_verifier import FakeCaptchaVerifier
from tests.backend.fakes.fake_hf_hub_client import FakeHFHubClient
from tests.backend.fakes.fake_hf_oauth_client import FakeHFOAuthClient
from tests.backend.fakes.fake_job_repository import FakeJobRepository
from tests.backend.fakes.fake_object_storage import FakeObjectStorage
from tests.backend.fakes.fake_user_repository import FakeUserRepository


class Fakes:
    def __init__(self) -> None:
        self.user_repository = FakeUserRepository()
        self.job_repository = FakeJobRepository()
        self.storage = FakeObjectStorage()
        self.hf_hub_client = FakeHFHubClient()
        self.captcha_verifier = FakeCaptchaVerifier()
        self.hf_oauth_client = FakeHFOAuthClient()


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


@pytest.fixture
def app(fakes: Fakes):
    settings = Settings(jwt_secret="test-jwt-secret", scheduler_shared_secret="test-scheduler-secret")
    deps = build_dependencies(
        settings,
        user_repository=fakes.user_repository,
        job_repository=fakes.job_repository,
        storage=fakes.storage,
        hf_hub_client=fakes.hf_hub_client,
        captcha_verifier=fakes.captcha_verifier,
        hf_oauth_client=fakes.hf_oauth_client,
    )
    return build_app(settings=settings, deps=deps)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers(client: TestClient):
    def _register_and_login(email: str = "a@example.com", password: str = "password123") -> dict[str, str]:
        client.post(
            "/auth/register",
            json={"email": email, "password": password, "captcha_token": "tok"},
        )
        response = client.post("/auth/login", json={"email": email, "password": password})
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _register_and_login
