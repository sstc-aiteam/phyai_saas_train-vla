"""Real Firestore-backed UserRepository. See job_repository.py for notes
on scope (thin translation layer, not unit-tested here)."""

from __future__ import annotations

from datetime import date

from google.cloud import firestore

from common.models import AuthProvider, User
from common.ports.user_repository import UserRepository

COLLECTION = "users"


def _user_to_doc(user: User) -> dict:
    return {
        "auth_provider": user.auth_provider.value,
        "email": user.email,
        "password_hash": user.password_hash,
        "hf_user_id": user.hf_user_id,
        "daily_quota_used": user.daily_quota_used,
        "quota_reset_date": user.quota_reset_date.isoformat() if user.quota_reset_date else None,
        "created_at": user.created_at,
    }


def _doc_to_user(user_id: str, doc: dict) -> User:
    quota_reset_date = doc.get("quota_reset_date")
    return User(
        id=user_id,
        auth_provider=AuthProvider(doc["auth_provider"]),
        email=doc.get("email"),
        password_hash=doc.get("password_hash"),
        hf_user_id=doc.get("hf_user_id"),
        daily_quota_used=doc.get("daily_quota_used", 0),
        quota_reset_date=date.fromisoformat(quota_reset_date) if quota_reset_date else None,
        created_at=doc["created_at"],
    )


class FirestoreUserRepository(UserRepository):
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION)

    def get(self, user_id: str) -> User | None:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return _doc_to_user(user_id, snapshot.to_dict())

    def get_by_email(self, email: str) -> User | None:
        query = self._collection.where("email", "==", email).limit(1)
        for snap in query.stream():
            return _doc_to_user(snap.id, snap.to_dict())
        return None

    def get_by_hf_user_id(self, hf_user_id: str) -> User | None:
        query = self._collection.where("hf_user_id", "==", hf_user_id).limit(1)
        for snap in query.stream():
            return _doc_to_user(snap.id, snap.to_dict())
        return None

    def create(self, user: User) -> None:
        self._collection.document(user.id).set(_user_to_doc(user))

    def update(self, user: User) -> None:
        self._collection.document(user.id).set(_user_to_doc(user))
