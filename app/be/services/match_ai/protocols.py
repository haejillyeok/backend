from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.be.models.game import GameSession, SessionParticipant, SessionPhase, WordTurn
from app.be.services.match_progress import MatchBroadcastEvent


class MatchAiTurnRepositoryProtocol(Protocol):
    async def get_game_session(self, game_session_public_id: UUID) -> GameSession | None:
        """AI 턴 조회 기준 game session row를 조회합니다."""

    async def get_active_turn_actor(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
    ) -> tuple[SessionPhase, WordTurn, SessionParticipant] | None:
        """현재 active turn phase와 actor row를 조회합니다."""

    async def list_used_words(self, *, session_id: UUID, round_number: int) -> list[str]:
        """현재 라운드에서 이미 사용한 정규화 단어 목록을 조회합니다."""


class MatchAiTurnProgressServiceProtocol(Protocol):
    async def submit_word(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        now: datetime,
    ) -> MatchBroadcastEvent:
        """AI가 낸 단어를 일반 참가자 제출과 같은 경로로 확정합니다."""

    async def reject_word(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        reason: str,
        details: dict[str, object] | None,
        now: datetime,
    ) -> MatchBroadcastEvent:
        """AI가 낸 단어의 규칙 위반을 일반 참가자 거절과 같은 경로로 확정합니다."""

    async def fail_ai_answer(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        reason: str,
        details: dict[str, object] | None = None,
    ) -> MatchBroadcastEvent | None:
        """Agent가 제출 단어를 만들지 못한 실패만 AI 실패로 확정합니다."""

    async def timeout_turn_if_due(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        now: datetime,
    ) -> MatchBroadcastEvent | None:
        """AI 답변이 deadline 이후 도착한 경우 timeout 확정 경로로 보냅니다."""
