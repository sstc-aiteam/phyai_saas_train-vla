from backend.security.password import hash_password, verify_password


def test_hash_is_not_the_plain_password():
    assert hash_password("secret123") != "secret123"


def test_verify_succeeds_for_correct_password():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed) is True


def test_verify_fails_for_wrong_password():
    hashed = hash_password("secret123")
    assert verify_password("wrong-password", hashed) is False


def test_two_hashes_of_same_password_differ():
    assert hash_password("secret123") != hash_password("secret123")
