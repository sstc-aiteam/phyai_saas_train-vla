"""Port: persistence for User documents (implemented by Firestore adapter / fakes)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from common.models import User


class UserRepository(ABC):
    @abstractmethod
    def get(self, user_id: str) -> User | None: ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def get_by_hf_user_id(self, hf_user_id: str) -> User | None: ...

    @abstractmethod
    def create(self, user: User) -> None: ...

    @abstractmethod
    def update(self, user: User) -> None: ...
