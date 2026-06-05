from uuid import RFC_4122

import pytest

from app.be.models.user import MAX_NICKNAME_LENGTH, User
from app.be.security.password import hash_password, verify_password
from app.shared.core.identifiers import generate_uuid_v7


def test_generate_uuid_v7_returns_rfc4122_uuid_v7():
    value = generate_uuid_v7()

    assert value.version == 7
    assert value.variant == RFC_4122


def test_password_hash_uses_salt_and_pbkdf2_sha256():
    first_hash = hash_password("secret-password")
    second_hash = hash_password("secret-password")

    assert first_hash.startswith("pbkdf2_sha256$")
    assert first_hash != second_hash
    assert "secret-password" not in first_hash
    assert verify_password("secret-password", first_hash)
    assert not verify_password("wrong-password", first_hash)


def test_user_rejects_nickname_longer_than_15_characters():
    with pytest.raises(ValueError, match="15자"):
        User(
            nickname="a" * (MAX_NICKNAME_LENGTH + 1),
            password_hash=hash_password("secret-password"),
        )
