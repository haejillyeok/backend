from hashlib import sha256
from secrets import token_urlsafe


SESSION_TOKEN_BYTES = 32
GAME_SESSION_TOKEN_BYTES = 32


def generate_session_token() -> str:
    """쿠키에 담아 클라이언트에 전달할 opaque 세션 토큰을 생성합니다."""
    return token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(session_token: str) -> str:
    """세션 토큰 원문 대신 저장할 SHA-256 해시 문자열을 반환합니다."""
    return sha256(session_token.encode("utf-8")).hexdigest()


def generate_game_session_token() -> str:
    """게임 참가자가 match 복구에 사용할 opaque 토큰을 생성합니다."""
    return token_urlsafe(GAME_SESSION_TOKEN_BYTES)


def hash_game_session_token(game_session_token: str) -> str:
    """게임 세션 토큰 원문 대신 저장할 SHA-256 해시 문자열을 반환합니다."""
    return sha256(game_session_token.encode("utf-8")).hexdigest()
