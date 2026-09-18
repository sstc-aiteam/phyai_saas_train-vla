from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: str, secret: str, expires_in: timedelta = timedelta(hours=12)) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + expires_in}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> str:
    """Return the user id encoded in the token, or raise InvalidTokenError."""
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    return payload["sub"]
