"""Real reCAPTCHA v3 verifier: calls Google's siteverify endpoint."""

from __future__ import annotations

import httpx

from common.ports.captcha_verifier import CaptchaResult, CaptchaVerifier

SITEVERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


class GoogleRecaptchaVerifier(CaptchaVerifier):
    def __init__(self, secret_key: str, http_client: httpx.Client | None = None) -> None:
        self._secret_key = secret_key
        self._http = http_client or httpx.Client(timeout=10.0)

    def verify(self, token: str) -> CaptchaResult:
        response = self._http.post(
            SITEVERIFY_URL, data={"secret": self._secret_key, "response": token}
        )
        body = response.json()
        return CaptchaResult(success=bool(body.get("success")), score=float(body.get("score", 0.0)))
