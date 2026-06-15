from collections.abc import Callable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.game import (
    GameSession,
    ScoreLedger,
    SessionParticipant,
    SessionPhase,
    SessionResult,
)
from app.be.models.game import UsedWord, WordTurn
from app.be.services.match import (
    MatchParticipantSnapshot,
    MatchResultSnapshot,
    MatchScoreSnapshot,
    MatchSnapshotResult,
    MatchTurnSnapshot,
)
from app.shared.core.timezone import kst_now


class MatchRepository:
    """match WebSocket snapshot 복구에 필요한 DB 조회를 담당합니다."""

    def __init__(self, db_session: AsyncSession, *, now_provider: Callable = kst_now) -> None:
        self.db_session = db_session
        self._now_provider = now_provider

    async def get_snapshot(
        self,
        *,
        game_session_public_id: UUID,
        participant_id: UUID,
    ) -> MatchSnapshotResult:
        """게임 세션의 현재 익명 참가자 목록, 사용 단어, 점수판 snapshot을 반환합니다."""
        session_result = await self.db_session.execute(
            select(GameSession).where(GameSession.public_id == game_session_public_id)
        )
        game_session = session_result.scalar_one_or_none()
        if game_session is None:
            return MatchSnapshotResult(
                game_session_public_id=game_session_public_id,
                status="aborted",
                rule_config={},
                participants=[],
                current_round_number=None,
                current_turn=None,
                used_words=[],
                scoreboard=[],
                server_time=self._now_provider(),
            )

        participant_result = await self.db_session.execute(
            select(SessionParticipant)
            .where(SessionParticipant.session_id == game_session.id)
            .order_by(SessionParticipant.seat_number.asc())
        )
        participants = list(participant_result.scalars().all())

        score_result = await self.db_session.execute(
            select(ScoreLedger.participant_id, func.coalesce(func.sum(ScoreLedger.score_delta), 0))
            .where(ScoreLedger.session_id == game_session.id)
            .group_by(ScoreLedger.participant_id)
        )
        scores_by_participant_id = {
            score_participant_id: int(score or 0)
            for score_participant_id, score in score_result.all()
        }
        current_turn = await self._get_current_turn(game_session)
        used_words = await self._list_used_words_for_current_round(
            game_session=game_session,
            current_turn=current_turn,
        )
        voting_deadline_at = await self._get_voting_deadline(game_session)
        results = await self._get_results(game_session, participant_id=participant_id)

        return MatchSnapshotResult(
            game_session_public_id=game_session.public_id,
            status=game_session.status,
            rule_config=game_session.rule_config,
            participants=[
                MatchParticipantSnapshot(
                    display_name=participant.display_name,
                    seat_number=participant.seat_number,
                    is_me=participant.id == participant_id,
                )
                for participant in participants
            ],
            current_round_number=current_turn.round_number if current_turn else None,
            current_turn=current_turn,
            used_words=used_words,
            scoreboard=[
                MatchScoreSnapshot(
                    display_name=participant.display_name,
                    seat_number=participant.seat_number,
                    score=scores_by_participant_id.get(participant.id, 0),
                    is_me=participant.id == participant_id,
                )
                for participant in participants
            ],
            server_time=self._now_provider(),
            voting_deadline_at=voting_deadline_at,
            results=results,
        )

    async def _list_used_words_for_current_round(
        self,
        *,
        game_session: GameSession,
        current_turn: MatchTurnSnapshot | None,
    ) -> list[str]:
        """현재 라운드 화면과 AI context에 맞춰 해당 라운드에서 사용된 단어만 조회합니다."""
        if current_turn is None:
            return []
        used_word_result = await self.db_session.execute(
            select(UsedWord)
            .where(
                UsedWord.session_id == game_session.id,
                UsedWord.round_number == current_turn.round_number,
            )
            .order_by(UsedWord.normalized_word.asc())
        )
        return [used_word.normalized_word for used_word in used_word_result.scalars().all()]

    async def _get_current_turn(self, game_session: GameSession) -> MatchTurnSnapshot | None:
        """세션의 current_phase_id가 가리키는 단어 턴 snapshot을 조회합니다."""
        if game_session.current_phase_id is None:
            return None

        turn_result = await self.db_session.execute(
            select(SessionPhase, WordTurn, SessionParticipant)
            .join(WordTurn, WordTurn.phase_id == SessionPhase.id)
            .join(SessionParticipant, SessionParticipant.id == WordTurn.participant_id)
            .where(
                SessionPhase.id == game_session.current_phase_id,
                SessionPhase.session_id == game_session.id,
            )
        )
        row = turn_result.one_or_none()
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

    async def _get_voting_deadline(self, game_session: GameSession):
        """voting 상태의 현재 phase deadline을 조회합니다."""
        if game_session.status != "voting" or game_session.current_phase_id is None:
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

    async def _get_results(
        self,
        game_session: GameSession,
        *,
        participant_id: UUID,
    ) -> list[MatchResultSnapshot]:
        """결과 상태 재접속 복구를 위해 참가자별 최종 결과 snapshot을 조회합니다."""
        if game_session.status != "result":
            return []

        result = await self.db_session.execute(
            select(SessionResult, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.id == SessionResult.participant_id)
            .where(SessionResult.session_id == game_session.id)
            .order_by(SessionParticipant.seat_number.asc())
        )
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
            )
            for session_result, participant in result.all()
        ]
