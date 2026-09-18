from __future__ import annotations

from common.ports.captcha_verifier import CaptchaResult, CaptchaVerifier


class FakeCaptchaVerifier(CaptchaVerifier):
    """Returns a configurable canned result regardless of the token given."""

    def __init__(self, result: CaptchaResult | None = None) -> None:
        self.result = result or CaptchaResult(success=True, score=0.9)
        self.calls: list[str] = []

    def verify(self, token: str) -> CaptchaResult:
        self.calls.append(token)
        return self.result
