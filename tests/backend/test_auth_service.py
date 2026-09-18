import pytest

from backend.services.auth_service import (
    AuthService,
    CaptchaFailedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)
from common.ports.captcha_verifier import CaptchaResult
from common.ports.hf_oauth_client import HFOAuthUser

from tests.backend.fakes.fake_captcha_verifier import FakeCaptchaVerifier
from tests.backend.fakes.fake_hf_oauth_client import FakeHFOAuthClient
from tests.backend.fakes.fake_user_repository import FakeUserRepository


@pytest.fixture
def service():
    return AuthService(
        user_repository=FakeUserRepository(),
        captcha_verifier=FakeCaptchaVerifier(),
        hf_oauth_client=FakeHFOAuthClient(),
    )


def test_register_with_email_succeeds(service):
    user = service.register_with_email("a@example.com", "password123", "captcha-token")
    assert user.email == "a@example.com"
    assert user.password_hash != "password123"


def test_register_rejects_low_captcha_score():
    service = AuthService(
        user_repository=FakeUserRepository(),
        captcha_verifier=FakeCaptchaVerifier(CaptchaResult(success=True, score=0.1)),
        hf_oauth_client=FakeHFOAuthClient(),
    )
    with pytest.raises(CaptchaFailedError):
        service.register_with_email("a@example.com", "password123", "captcha-token")


def test_register_rejects_duplicate_email(service):
    service.register_with_email("a@example.com", "password123", "captcha-token")
    with pytest.raises(EmailAlreadyRegisteredError):
        service.register_with_email("a@example.com", "different-password", "captcha-token")


def test_login_with_correct_password_succeeds(service):
    service.register_with_email("a@example.com", "password123", "captcha-token")
    user = service.login_with_email("a@example.com", "password123")
    assert user.email == "a@example.com"


def test_login_with_wrong_password_fails(service):
    service.register_with_email("a@example.com", "password123", "captcha-token")
    with pytest.raises(InvalidCredentialsError):
        service.login_with_email("a@example.com", "wrong-password")


def test_login_with_unknown_email_fails(service):
    with pytest.raises(InvalidCredentialsError):
        service.login_with_email("nobody@example.com", "password123")


def test_change_password_then_login_with_new_password(service):
    user = service.register_with_email("a@example.com", "password123", "captcha-token")
    service.change_password(user.id, "password123", "new-password456")
    logged_in = service.login_with_email("a@example.com", "new-password456")
    assert logged_in.id == user.id
    with pytest.raises(InvalidCredentialsError):
        service.login_with_email("a@example.com", "password123")


def test_change_password_rejects_wrong_old_password(service):
    user = service.register_with_email("a@example.com", "password123", "captcha-token")
    with pytest.raises(InvalidCredentialsError):
        service.change_password(user.id, "wrong-old-password", "new-password456")


def test_hf_oauth_login_creates_new_user_on_first_login(service):
    service._hf_oauth.register_code("code-1", HFOAuthUser(hf_user_id="hf-1", username="alice"))
    user = service.login_or_register_with_hf("code-1", "https://app.example.com/callback")
    assert user.hf_user_id == "hf-1"


def test_hf_oauth_login_reuses_existing_user_on_second_login(service):
    service._hf_oauth.register_code("code-1", HFOAuthUser(hf_user_id="hf-1", username="alice"))
    first = service.login_or_register_with_hf("code-1", "https://app.example.com/callback")

    service._hf_oauth.register_code("code-2", HFOAuthUser(hf_user_id="hf-1", username="alice"))
    second = service.login_or_register_with_hf("code-2", "https://app.example.com/callback")

    assert first.id == second.id


def test_email_and_hf_accounts_are_independent(service):
    email_user = service.register_with_email("alice@example.com", "password123", "captcha-token")
    service._hf_oauth.register_code("code-1", HFOAuthUser(hf_user_id="hf-1", username="alice", email="alice@example.com"))
    hf_user = service.login_or_register_with_hf("code-1", "https://app.example.com/callback")

    assert email_user.id != hf_user.id
