from hashlib import pbkdf2_hmac
from hmac import compare_digest
from secrets import token_hex


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 120_000
PASSWORD_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """비밀번호를 salt가 포함된 PBKDF2-HMAC-SHA256 문자열로 변환합니다."""
    salt = token_hex(PASSWORD_SALT_BYTES)
    digest = _derive_password_digest(password, salt, PASSWORD_HASH_ITERATIONS)
    return f"{PASSWORD_HASH_ALGORITHM}${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded_password_hash: str) -> bool:
    """입력 비밀번호가 저장된 PBKDF2-HMAC-SHA256 hash와 일치하는지 검증합니다."""
    try:
        algorithm, iterations, salt, expected_digest = encoded_password_hash.split("$")
    except ValueError:
        return False

    if algorithm != PASSWORD_HASH_ALGORITHM:
        return False

    try:
        iteration_count = int(iterations)
    except ValueError:
        return False

    actual_digest = _derive_password_digest(password, salt, iteration_count)
    return compare_digest(actual_digest, expected_digest)


def _derive_password_digest(password: str, salt: str, iterations: int) -> str:
    digest = pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    )
    return digest.hex()
