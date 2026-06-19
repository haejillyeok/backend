from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.game import (
    GameSession,
    ScoreLedger,
    SessionParticipant,
    SessionPhase,
    SessionResult,
    UsedWord,
    WordTurn,
)
from app.be.services.match.snapshots import MatchResultSnapshot, MatchTurnSnapshot
from app.be.services.match_vote import ScoreBreakdownItem
from app.be.services.match_vote.result_policy import MatchVoteResultPolicy


class MatchRepository:
    """match 도메인의 snapshot 복구에 필요한 DB query step을 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def get_game_session(self, *, game_session_public_id: UUID) -> GameSession | None:
        """public_id로 game_session row 하나를 조회합니다."""
        result = await self.db_session.execute(
            select(GameSession).where(GameSession.public_id == game_session_public_id)
        )
        return result.scalar_one_or_none()

    async def list_participants(self, *, game_session_id: UUID) -> list[SessionParticipant]:
        """game_session 참가자 snapshot row를 seat 순서로 조회합니다."""
        result = await self.db_session.execute(
            select(SessionParticipant)
            .where(SessionParticipant.session_id == game_session_id)
            .order_by(SessionParticipant.seat_number.asc())
        )
        return list(result.scalars().all())

    async def list_score_totals(self, *, game_session_id: UUID) -> dict[UUID, int]:
        """참가자별 누적 점수 합계를 조회합니다."""
        result = await self.db_session.execute(
            select(ScoreLedger.participant_id, func.coalesce(func.sum(ScoreLedger.score_delta), 0))
            .where(ScoreLedger.session_id == game_session_id)
            .group_by(ScoreLedger.participant_id)
        )
        return {participant_id: int(score or 0) for participant_id, score in result.all()}

    async def get_current_turn(self, *, game_session: GameSession) -> MatchTurnSnapshot | None:
        """세션의 current_phase_id가 가리키는 단어 턴 snapshot을 조회합니다."""
        if game_session.current_phase_id is None:
            return None
        result = await self.db_session.execute(
            select(SessionPhase, WordTurn, SessionParticipant)
            .join(WordTurn, WordTurn.phase_id == SessionPhase.id)
            .join(SessionParticipant, SessionParticipant.id == WordTurn.participant_id)
            .where(
                SessionPhase.id == game_session.current_phase_id,
                SessionPhase.session_id == game_session.id,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        phase, turn, participant = row
        return MatchTurnSnapshot(
            phase_id=phase.id,
            round_number=turn.round_number,
            turn_number=turn.turn_number,
            actor_seat_number=participant.seat_number,
            started_at=phase.started_at,
            deadline_at=phase.deadline_at,
            required_start_char=turn.condition_payload.get("required_start_char"),
        )

    async def list_used_words_for_round(
        self,
        *,
        game_session_id: UUID,
        round_number: int,
    ) -> list[str]:
        """해당 라운드에서 사용된 단어를 정규화 단어 기준으로 조회합니다."""
        result = await self.db_session.execute(
            select(UsedWord)
            .where(
                UsedWord.session_id == game_session_id,
                UsedWord.round_number == round_number,
            )
            .order_by(UsedWord.normalized_word.asc())
        )
        return [used_word.normalized_word for used_word in result.scalars().all()]

    async def get_voting_deadline(self, *, game_session: GameSession) -> datetime | None:
        """voting 상태의 현재 phase deadline을 조회합니다."""
        if game_session.current_phase_id is None:
            return None
        result = await self.db_session.execute(
            select(SessionPhase).where(
                SessionPhase.id == game_session.current_phase_id,
                SessionPhase.session_id == game_session.id,
                SessionPhase.phase_type == "voting",
            )
        )
        phase = result.scalar_one_or_none()
        if phase is None:
            return None
        return phase.deadline_at

    async def list_results(
        self,
        *,
        game_session_id: UUID,
        participant_id: UUID,
    ) -> list[MatchResultSnapshot]:
        """참가자별 최종 결과 snapshot row를 seat 순서로 조회합니다."""
        score_breakdown_items = await self._list_score_breakdown_items(game_session_id)
        result = await self.db_session.execute(
            select(SessionResult, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.id == SessionResult.participant_id)
            .where(SessionResult.session_id == game_session_id)
            .order_by(SessionParticipant.seat_number.asc())
        )
        result_policy = MatchVoteResultPolicy()
        return [
            MatchResultSnapshot(
                display_name=participant.display_name,
                seat_number=participant.seat_number,
                revealed_participant_type=session_result.revealed_participant_type,
                final_score=session_result.final_score,
                rank=session_result.rank,
                is_winner=session_result.is_winner,
                vote_score_delta=int(session_result.result_payload.get("vote_score_delta", 0)),
                is_me=participant.id == participant_id,
                score_breakdown=result_policy.build_score_breakdown(
                    score_breakdown_items.get(participant.id, [])
                ),
            )
            for session_result, participant in result.all()
        ]

    async def _list_score_breakdown_items(
        self,
        game_session_id: UUID,
    ) -> dict[UUID, list[ScoreBreakdownItem]]:
        """결과 재접속 snapshot용 점수 원장 항목을 참가자별로 조회합니다."""
        result = await self.db_session.execute(
            select(ScoreLedger.participant_id, ScoreLedger.reason, ScoreLedger.score_delta)
            .where(ScoreLedger.session_id == game_session_id)
            .order_by(ScoreLedger.participant_id.asc(), ScoreLedger.created_at.asc())
        )
        breakdown_by_participant_id: dict[UUID, list[ScoreBreakdownItem]] = {}
        for row_participant_id, reason, score_delta in result.all():
            breakdown_by_participant_id.setdefault(row_participant_id, []).append(
                ScoreBreakdownItem(reason=reason, score_delta=int(score_delta))
            )
        return breakdown_by_participant_id
