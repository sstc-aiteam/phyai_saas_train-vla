from __future__ import annotations

from common.ports.hf_oauth_client import HFOAuthClient, HFOAuthUser


class FakeHFOAuthClient(HFOAuthClient):
    """Test setup registers which HF user a given auth code resolves to."""

    def __init__(self) -> None:
        self._codes: dict[str, HFOAuthUser] = {}

    def register_code(self, code: str, user: HFOAuthUser) -> None:
        self._codes[code] = user

    def exchange_code_for_user(self, code: str, redirect_uri: str) -> HFOAuthUser:
        if code not in self._codes:
            raise ValueError("Invalid or expired OAuth code")
        return self._codes[code]
