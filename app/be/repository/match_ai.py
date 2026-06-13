from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.game import GameSession, SessionParticipant, SessionPhase, UsedWord, WordTurn
from app.be.schemas.game_enum import ParticipantType
from app.be.services.match_ai import AiTurnContext
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


class MatchAiTurnRepository:
    """AI 턴 Agent 요청에 필요한 현재 세션 상태를 조회합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def get_ai_turn_context(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
    ) -> AiTurnContext | None:
        """현재 phase actor가 AI이면 used words와 단어 조건을 포함한 context를 반환합니다."""
        session_result = await self.db_session.execute(
            select(GameSession).where(GameSession.public_id == game_session_public_id)
        )
        game_session = session_result.scalar_one_or_none()
        if game_session is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "game_session_not_found"},
            )

        turn_result = await self.db_session.execute(
            select(SessionPhase, WordTurn, SessionParticipant)
            .join(WordTurn, WordTurn.phase_id == SessionPhase.id)
            .join(SessionParticipant, SessionParticipant.id == WordTurn.participant_id)
            .where(
                SessionPhase.id == phase_id,
                SessionPhase.session_id == game_session.id,
                SessionPhase.finished_at.is_(None),
            )
        )
        row = turn_result.one_or_none()
        if row is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "active_turn_not_found"},
            )
        phase, turn, participant = row
        if participant.participant_type != ParticipantType.AI.value:
            return None

        used_word_result = await self.db_session.execute(
            select(UsedWord)
            .where(UsedWord.session_id == game_session.id)
            .order_by(UsedWord.normalized_word.asc())
        )
        used_words = [used_word.normalized_word for used_word in used_word_result.scalars().all()]
        return AiTurnContext(
            game_session_public_id=game_session.public_id,
            phase_id=phase.id,
            participant_id=participant.id,
            game_type=game_session.game_type,
            used_words=used_words,
            required_start_char=turn.condition_payload.get("required_start_char"),
        )
