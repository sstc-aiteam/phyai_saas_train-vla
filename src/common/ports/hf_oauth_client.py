"""Port: Hugging Face OAuth code exchange, used for the "login with HF" flow."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class HFOAuthUser:
    hf_user_id: str
    username: str
    email: str | None = None


class HFOAuthClient(ABC):
    @abstractmethod
    def exchange_code_for_user(self, code: str, redirect_uri: str) -> HFOAuthUser: ...
