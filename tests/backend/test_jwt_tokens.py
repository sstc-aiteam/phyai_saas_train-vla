from datetime import timedelta

import pytest

from backend.security.jwt_tokens import InvalidTokenError, create_access_token, decode_access_token

SECRET = "test-secret"


def test_roundtrip():
    token = create_access_token("user-1", SECRET)
    assert decode_access_token(token, SECRET) == "user-1"


def test_decode_fails_with_wrong_secret():
    token = create_access_token("user-1", SECRET)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, "different-secret")


def test_decode_fails_for_expired_token():
    token = create_access_token("user-1", SECRET, expires_in=timedelta(seconds=-1))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_decode_fails_for_garbage_token():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt", SECRET)
