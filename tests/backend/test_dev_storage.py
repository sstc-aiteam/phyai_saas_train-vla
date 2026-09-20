import pytest
from fastapi.testclient import TestClient

from backend.adapters.memory import (
    InMemoryCaptchaVerifier,
    InMemoryHFHubClient,
    InMemoryHFOAuthClient,
    InMemoryJobRepository,
    InMemoryObjectStorage,
    InMemoryUserRepository,
)
from backend.config import Settings
from backend.deps import build_dependencies
from backend.main import build_app


@pytest.fixture
def client() -> TestClient:
    settings = Settings(use_fake_adapters=True)
    deps = build_dependencies(
        settings,
        user_repository=InMemoryUserRepository(),
        job_repository=InMemoryJobRepository(),
        storage=InMemoryObjectStorage(base_url="http://testserver"),
        hf_hub_client=InMemoryHFHubClient(),
        captcha_verifier=InMemoryCaptchaVerifier(),
        hf_oauth_client=InMemoryHFOAuthClient(),
    )
    app = build_app(settings=settings, deps=deps)
    return TestClient(app)


def test_put_then_get_round_trips_bytes(client: TestClient):
    put_response = client.put("/dev-storage/uploads/u1/a.zip", content=b"hello world")
    assert put_response.status_code == 204

    get_response = client.get("/dev-storage/uploads/u1/a.zip")
    assert get_response.status_code == 200
    assert get_response.content == b"hello world"


def test_get_missing_object_returns_404(client: TestClient):
    response = client.get("/dev-storage/uploads/does/not-exist.zip")
    assert response.status_code == 404


def test_generated_upload_url_is_a_real_dev_storage_route(client: TestClient):
    # Confirm the router path matches what InMemoryObjectStorage generates.
    storage = InMemoryObjectStorage(base_url="http://testserver")
    url = storage.generate_upload_url("uploads/u1/a.zip", "application/zip", 900)
    assert url == "http://testserver/dev-storage/uploads/u1/a.zip"


def test_dev_storage_not_mounted_when_using_non_memory_storage():
    from backend.adapters.memory import InMemoryHFOAuthClient as _NoopOAuth  # keep import list tidy

    from tests.backend.fakes.fake_captcha_verifier import FakeCaptchaVerifier
    from tests.backend.fakes.fake_hf_hub_client import FakeHFHubClient
    from tests.backend.fakes.fake_job_repository import FakeJobRepository
    from tests.backend.fakes.fake_object_storage import FakeObjectStorage
    from tests.backend.fakes.fake_user_repository import FakeUserRepository

    settings = Settings(use_fake_adapters=True)
    deps = build_dependencies(
        settings,
        user_repository=FakeUserRepository(),
        job_repository=FakeJobRepository(),
        storage=FakeObjectStorage(),
        hf_hub_client=FakeHFHubClient(),
        captcha_verifier=FakeCaptchaVerifier(),
        hf_oauth_client=_NoopOAuth(),
    )
    app = build_app(settings=settings, deps=deps)
    client = TestClient(app)

    response = client.put("/dev-storage/uploads/u1/a.zip", content=b"hello")
    assert response.status_code == 404
