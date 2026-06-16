from typing import Protocol
from uuid import UUID

from app.be.models.game import GameSession, SessionParticipant
from app.be.services.match.snapshots import MatchResultSnapshot, MatchTurnSnapshot


class MatchRepositoryProtocol(Protocol):
    async def get_game_session(self, *, game_session_public_id: UUID) -> GameSession | None:
        """public_id로 game_session row 하나를 조회합니다."""

    async def list_participants(self, *, game_session_id: UUID) -> list[SessionParticipant]:
        """game_session 참가자 snapshot row를 seat 순서로 조회합니다."""

    async def list_score_totals(self, *, game_session_id: UUID) -> dict[UUID, int]:
        """참가자별 누적 점수 합계를 조회합니다."""

    async def get_current_turn(self, *, game_session: GameSession) -> MatchTurnSnapshot | None:
        """game_session의 현재 단어 턴 정보를 조회합니다."""

    async def list_used_words_for_round(
        self,
        *,
        game_session_id: UUID,
        round_number: int,
    ) -> list[str]:
        """해당 라운드에서 사용된 단어를 조회합니다."""

    async def get_voting_deadline(self, *, game_session: GameSession):
        """voting phase deadline을 조회합니다."""

    async def list_results(
        self,
        *,
        game_session_id: UUID,
        participant_id: UUID,
    ) -> list[MatchResultSnapshot]:
        """참가자별 최종 결과 snapshot을 조회합니다."""
