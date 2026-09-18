"""Registration / login / password-change / HF-OAuth-login use cases.

Per spec: two independent auth methods (email+password, or HF OAuth), each
with its own account and quota — no account linking in this version. Email
signup has no email verification and no self-service password reset.
"""

from __future__ import annotations

import dataclasses
import uuid

from common.models import AuthProvider, User, utcnow
from common.ports.captcha_verifier import CaptchaVerifier
from common.ports.hf_oauth_client import HFOAuthClient
from common.ports.user_repository import UserRepository

from backend.security.password import hash_password, verify_password

MIN_CAPTCHA_SCORE = 0.5


class CaptchaFailedError(Exception):
    pass


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        captcha_verifier: CaptchaVerifier,
        hf_oauth_client: HFOAuthClient,
        min_captcha_score: float = MIN_CAPTCHA_SCORE,
        now_fn=utcnow,
    ) -> None:
        self._users = user_repository
        self._captcha = captcha_verifier
        self._hf_oauth = hf_oauth_client
        self._min_captcha_score = min_captcha_score
        self._now = now_fn

    def register_with_email(self, email: str, password: str, captcha_token: str) -> User:
        captcha_result = self._captcha.verify(captcha_token)
        if not captcha_result.success or captcha_result.score < self._min_captcha_score:
            raise CaptchaFailedError("reCAPTCHA verification failed")

        if self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(f"Email already registered: {email}")

        user = User(
            id=str(uuid.uuid4()),
            auth_provider=AuthProvider.EMAIL,
            email=email,
            password_hash=hash_password(password),
            created_at=self._now(),
        )
        self._users.create(user)
        return user

    def login_with_email(self, email: str, password: str) -> User:
        user = self._users.get_by_email(email)
        if user is None or user.password_hash is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid email or password")
        return user

    def change_password(self, user_id: str, old_password: str, new_password: str) -> User:
        user = self._users.get(user_id)
        if user is None or user.password_hash is None:
            raise InvalidCredentialsError("User not found or has no password set")
        if not verify_password(old_password, user.password_hash):
            raise InvalidCredentialsError("Old password is incorrect")

        updated = dataclasses.replace(user, password_hash=hash_password(new_password))
        self._users.update(updated)
        return updated

    def login_or_register_with_hf(self, code: str, redirect_uri: str) -> User:
        hf_user = self._hf_oauth.exchange_code_for_user(code, redirect_uri)

        existing = self._users.get_by_hf_user_id(hf_user.hf_user_id)
        if existing is not None:
            return existing

        user = User(
            id=str(uuid.uuid4()),
            auth_provider=AuthProvider.HUGGINGFACE,
            email=hf_user.email,
            hf_user_id=hf_user.hf_user_id,
            created_at=self._now(),
        )
        self._users.create(user)
        return user
