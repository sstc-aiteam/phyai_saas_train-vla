from __future__ import annotations

import dataclasses

from common.models import User
from common.ports.user_repository import UserRepository


class FakeUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def get(self, user_id: str) -> User | None:
        user = self._users.get(user_id)
        return dataclasses.replace(user) if user else None

    def get_by_email(self, email: str) -> User | None:
        for user in self._users.values():
            if user.email == email:
                return dataclasses.replace(user)
        return None

    def get_by_hf_user_id(self, hf_user_id: str) -> User | None:
        for user in self._users.values():
            if user.hf_user_id == hf_user_id:
                return dataclasses.replace(user)
        return None

    def create(self, user: User) -> None:
        if user.id in self._users:
            raise ValueError(f"User {user.id} already exists")
        self._users[user.id] = dataclasses.replace(user)

    def update(self, user: User) -> None:
        if user.id not in self._users:
            raise KeyError(f"User {user.id} does not exist")
        self._users[user.id] = dataclasses.replace(user)
