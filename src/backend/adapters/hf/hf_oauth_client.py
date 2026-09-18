"""Real Hugging Face OAuth adapter: exchanges an authorization code for an
access token, then fetches the HF user's profile."""

from __future__ import annotations

import httpx

from common.ports.hf_oauth_client import HFOAuthClient, HFOAuthUser

TOKEN_URL = "https://huggingface.co/oauth/token"
USERINFO_URL = "https://huggingface.co/oauth/userinfo"


class OAuthExchangeError(Exception):
    pass


class RealHFOAuthClient(HFOAuthClient):
    def __init__(self, client_id: str, client_secret: str, http_client: httpx.Client | None = None) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http_client or httpx.Client(timeout=10.0)

    def exchange_code_for_user(self, code: str, redirect_uri: str) -> HFOAuthUser:
        token_response = self._http.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        if token_response.status_code != 200:
            raise OAuthExchangeError(f"HF OAuth token exchange failed: {token_response.text}")
        access_token = token_response.json()["access_token"]

        userinfo_response = self._http.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if userinfo_response.status_code != 200:
            raise OAuthExchangeError(f"HF OAuth userinfo request failed: {userinfo_response.text}")
        userinfo = userinfo_response.json()

        return HFOAuthUser(
            hf_user_id=str(userinfo["sub"]),
            username=userinfo.get("preferred_username", userinfo.get("name", "")),
            email=userinfo.get("email"),
        )
