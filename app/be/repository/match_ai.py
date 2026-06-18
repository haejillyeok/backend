from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.game import GameSession, SessionParticipant, SessionPhase, UsedWord, WordTurn


class MatchAiTurnRepository:
    """AI 턴 Agent 요청에 필요한 현재 세션 상태를 조회합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def get_game_session(self, game_session_public_id: UUID) -> GameSession | None:
        """AI 턴 조회 기준 game session row를 조회합니다."""
        result = await self.db_session.execute(
            select(GameSession).where(GameSession.public_id == game_session_public_id)
        )
        return result.scalar_one_or_none()

    async def get_active_turn_actor(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
    ) -> tuple[SessionPhase, WordTurn, SessionParticipant] | None:
        """현재 active turn phase와 actor row를 조회합니다."""
        result = await self.db_session.execute(
            select(SessionPhase, WordTurn, SessionParticipant)
            .join(WordTurn, WordTurn.phase_id == SessionPhase.id)
            .join(SessionParticipant, SessionParticipant.id == WordTurn.participant_id)
            .where(
                SessionPhase.id == phase_id,
                SessionPhase.session_id == session_id,
                SessionPhase.finished_at.is_(None),
            )
        )
        return result.one_or_none()

    async def list_used_words(self, *, session_id: UUID, round_number: int) -> list[str]:
        """현재 라운드에서 이미 사용한 정규화 단어 목록을 조회합니다."""
        result = await self.db_session.execute(
            select(UsedWord)
            .where(
                UsedWord.session_id == session_id,
                UsedWord.round_number == round_number,
            )
            .order_by(UsedWord.normalized_word.asc())
        )
        return [used_word.normalized_word for used_word in result.scalars().all()]
