"""Port: reCAPTCHA v3 score verification for the email/password registration form."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CaptchaResult:
    success: bool
    score: float


class CaptchaVerifier(ABC):
    @abstractmethod
    def verify(self, token: str) -> CaptchaResult: ...
