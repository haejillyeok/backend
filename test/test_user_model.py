from uuid import RFC_4122

import pytest

from app.be.models.user import MAX_ACCOUNT_ID_LENGTH, MAX_NICKNAME_LENGTH, User
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


def test_user_rejects_account_id_longer_than_20_characters():
    with pytest.raises(ValueError, match="20자"):
        User(
            account_id="a" * (MAX_ACCOUNT_ID_LENGTH + 1),
            nickname="초보자",
            password_hash=hash_password("secret-password"),
        )


def test_user_rejects_account_id_with_non_ascii_word_characters():
    with pytest.raises(ValueError, match="문자, 숫자, _"):
        User(
            account_id="한글id",
            nickname="초보자",
            password_hash=hash_password("secret-password"),
        )


def test_user_rejects_nickname_longer_than_20_characters():
    with pytest.raises(ValueError, match="20자"):
        User(
            account_id="player_001",
            nickname="a" * (MAX_NICKNAME_LENGTH + 1),
            password_hash=hash_password("secret-password"),
        )


def test_user_rejects_nickname_with_special_characters():
    with pytest.raises(ValueError, match="한글, 영어, 숫자, _"):
        User(
            account_id="player_001",
            nickname="초보자!",
            password_hash=hash_password("secret-password"),
        )
