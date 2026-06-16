from app.be.security.session import generate_game_session_token, hash_game_session_token
from app.be.services.game.records import GAME_SESSION_TOKEN_TTL, GameSessionCredential
from app.shared.core.timezone import kst_now


class SessionCredentialPolicy:
    """match 재접속에 사용할 게임 세션 토큰 발급과 해시 생성을 관리합니다."""

    def issue(self) -> GameSessionCredential:
        """현재 시각 기준 만료 시각을 가진 새 게임 세션 토큰을 발급합니다."""
        return GameSessionCredential(
            game_session_token=generate_game_session_token(),
            expires_at=kst_now() + GAME_SESSION_TOKEN_TTL,
        )

    def hash_token(self, game_session_token: str) -> str:
        """저장소에 원문 토큰을 남기지 않도록 세션 토큰 해시를 반환합니다."""
        return hash_game_session_token(game_session_token)
