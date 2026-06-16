from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.game import (
    GameEvent,
    GameSession,
    ParticipantAction,
    Room,
    ScoreLedger,
    SessionParticipant,
    SessionPhase,
    SessionResult,
    Vote,
)
from app.be.repository.match_vote.constants import (
    RESULT_PUBLISHED_EVENT_TYPE,
    VOTE_ACCEPTED_EVENT_TYPE,
    VOTE_SUBMIT_ACTION_TYPE,
    VOTE_TIMEOUT_EVENT_TYPE,
)
from app.be.schemas.game_enum import GameSessionStatus, RoomStatus
from app.be.services.match_vote.records import MatchResultParticipantPayload
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException
from app.shared.core.identifiers import generate_uuid_v7


class MatchVoteRepository:
    """AI 지목 투표 도메인의 DB 조회와 변경 실행을 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def get_game_session_for_update(self, public_id: UUID) -> GameSession:
        """투표 처리 기준 game session row를 잠그고 조회합니다."""
        result = await self.db_session.execute(
            select(GameSession).where(GameSession.public_id == public_id).with_for_update()
        )
        game_session = result.scalar_one_or_none()
        if game_session is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "game_session_not_found"},
            )
        return game_session

    async def get_room_for_update(self, room_id: UUID) -> Room:
        """결과 확정 후 room 상태를 바꾸기 위해 room row를 잠그고 조회합니다."""
        result = await self.db_session.execute(
            select(Room).where(Room.id == room_id).with_for_update()
        )
        room = result.scalar_one_or_none()
        if room is None:
            raise AppException(
                code=ErrorCode.GAME_ROOM_NOT_FOUND,
                details={"reason": "room_not_found"},
            )
        return room

    async def get_voting_phase(self, *, game_session: GameSession) -> SessionPhase | None:
        """현재 voting phase row를 조회합니다."""
        if game_session.current_phase_id is None:
            return None
        result = await self.db_session.execute(
            select(SessionPhase).where(
                SessionPhase.id == game_session.current_phase_id,
                SessionPhase.session_id == game_session.id,
                SessionPhase.phase_type == "voting",
            )
        )
        return result.scalar_one_or_none()

    async def get_participant(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
    ) -> SessionParticipant:
        """세션 안의 참가자를 참가자 id로 조회합니다."""
        result = await self.db_session.execute(
            select(SessionParticipant).where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.id == participant_id,
            )
        )
        participant = result.scalar_one_or_none()
        if participant is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "participant_not_found"},
            )
        return participant

    async def get_participant_by_seat_number(
        self,
        *,
        session_id: UUID,
        seat_number: int,
    ) -> SessionParticipant:
        """세션 안의 참가자를 좌석 번호로 조회합니다."""
        result = await self.db_session.execute(
            select(SessionParticipant).where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.seat_number == seat_number,
            )
        )
        participant = result.scalar_one_or_none()
        if participant is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "target_participant_not_found"},
            )
        return participant

    async def list_participants(self, session_id: UUID) -> list[SessionParticipant]:
        """세션 참가자 목록을 좌석 번호 순서로 조회합니다."""
        result = await self.db_session.execute(
            select(SessionParticipant)
            .where(SessionParticipant.session_id == session_id)
            .order_by(SessionParticipant.seat_number.asc())
        )
        return list(result.scalars().all())

    async def list_votes(self, session_id: UUID) -> list[Vote]:
        """세션에 제출된 vote row 목록을 조회합니다."""
        result = await self.db_session.execute(select(Vote).where(Vote.session_id == session_id))
        return list(result.scalars().all())

    async def get_score_totals(self, session_id: UUID) -> dict[UUID, int]:
        """투표 결과 계산을 위한 참가자별 누적 점수를 조회합니다."""
        result = await self.db_session.execute(
            select(ScoreLedger.participant_id, func.coalesce(func.sum(ScoreLedger.score_delta), 0))
            .where(ScoreLedger.session_id == session_id)
            .group_by(ScoreLedger.participant_id)
        )
        return {participant_id: int(score or 0) for participant_id, score in result.all()}

    async def get_next_action_number(self, session_id: UUID) -> int:
        """다음 participant action 번호를 조회합니다."""
        result = await self.db_session.execute(
            select(func.coalesce(func.max(ParticipantAction.action_number), 0)).where(
                ParticipantAction.session_id == session_id
            )
        )
        return int(result.scalar_one()) + 1

    async def get_next_event_sequence(self, session_id: UUID) -> int:
        """다음 game event sequence를 조회합니다."""
        result = await self.db_session.execute(
            select(func.coalesce(func.max(GameEvent.sequence), 0)).where(
                GameEvent.session_id == session_id
            )
        )
        return int(result.scalar_one()) + 1

    async def create_vote_submit_action(
        self,
        *,
        session_id: UUID,
        voter: SessionParticipant,
        target: SessionParticipant,
        action_number: int,
        now: datetime,
    ) -> ParticipantAction:
        """투표 제출 action row 하나를 session에 추가합니다."""
        action = ParticipantAction(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=None,
            participant_id=voter.id,
            action_type=VOTE_SUBMIT_ACTION_TYPE,
            action_number=action_number,
            attempt_number=1,
            payload={"target_seat_number": target.seat_number},
            submitted_at=now,
            response_ms=None,
            is_valid=True,
        )
        self.db_session.add(action)
        return action

    async def create_vote(
        self,
        *,
        session_id: UUID,
        voter: SessionParticipant,
        target: SessionParticipant,
        is_correct: bool,
        now: datetime,
    ) -> Vote:
        """투표 선택 row 하나를 session에 추가합니다."""
        vote = Vote(
            id=generate_uuid_v7(),
            session_id=session_id,
            voter_participant_id=voter.id,
            target_participant_id=target.id,
            voted_at=now,
            is_correct=is_correct,
        )
        self.db_session.add(vote)
        return vote

    async def create_vote_accepted_event(
        self,
        *,
        session_id: UUID,
        voter: SessionParticipant,
        action: ParticipantAction,
        event_sequence: int,
        submitted_vote_count: int,
        required_vote_count: int,
        now: datetime,
    ) -> GameEvent:
        """투표 접수 event row 하나를 session에 추가합니다."""
        event = GameEvent(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=None,
            participant_id=voter.id,
            action_id=action.id,
            sequence=event_sequence,
            event_type=VOTE_ACCEPTED_EVENT_TYPE,
            payload={
                "voter": {
                    "display_name": voter.display_name,
                    "seat_number": voter.seat_number,
                },
                "submitted_vote_count": submitted_vote_count,
                "required_vote_count": required_vote_count,
            },
            created_at=now,
        )
        self.db_session.add(event)
        return event

    async def create_vote_timeout_event(
        self,
        *,
        session_id: UUID,
        event_sequence: int,
        submitted_vote_count: int,
        required_vote_count: int,
        now: datetime,
    ) -> GameEvent:
        """투표 timeout event row 하나를 session에 추가합니다."""
        event = GameEvent(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=None,
            participant_id=None,
            action_id=None,
            sequence=event_sequence,
            event_type=VOTE_TIMEOUT_EVENT_TYPE,
            payload={
                "submitted_vote_count": submitted_vote_count,
                "required_vote_count": required_vote_count,
            },
            created_at=now,
        )
        self.db_session.add(event)
        return event

    async def create_vote_score_ledger(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
        source_vote_id: UUID,
        reason: str,
        score_delta: int,
        now: datetime,
    ) -> ScoreLedger:
        """투표 결과 점수 ledger row 하나를 session에 추가합니다."""
        ledger = ScoreLedger(
            id=generate_uuid_v7(),
            session_id=session_id,
            participant_id=participant_id,
            source_type="vote",
            source_id=source_vote_id,
            reason=reason,
            score_delta=score_delta,
            created_at=now,
        )
        self.db_session.add(ledger)
        return ledger

    async def create_session_result(
        self,
        *,
        session_id: UUID,
        participant: SessionParticipant,
        result: MatchResultParticipantPayload,
        now: datetime,
    ) -> SessionResult:
        """참가자 최종 결과 row 하나를 session에 추가합니다."""
        session_result = SessionResult(
            id=generate_uuid_v7(),
            session_id=session_id,
            participant_id=participant.id,
            final_score=result.final_score,
            rank=result.rank,
            is_winner=result.is_winner,
            revealed_participant_type=result.revealed_participant_type,
            result_payload={"vote_score_delta": result.vote_score_delta},
            created_at=now,
        )
        self.db_session.add(session_result)
        return session_result

    async def mark_game_session_result(
        self,
        *,
        game_session: GameSession,
        now: datetime,
    ) -> None:
        """게임 세션 row 하나를 결과 상태로 변경합니다."""
        game_session.status = GameSessionStatus.RESULT.value
        game_session.ended_at = now

    async def mark_room_waiting(self, *, room: Room, now: datetime) -> None:
        """게임 종료 후 room row 하나를 대기 상태로 변경합니다."""
        room.status = RoomStatus.WAITING.value
        room.updated_at = now

    async def create_result_published_event(
        self,
        *,
        session_id: UUID,
        event_sequence: int,
        results: list[MatchResultParticipantPayload],
        now: datetime,
    ) -> GameEvent:
        """결과 발표 event row 하나를 session에 추가합니다."""
        event = GameEvent(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=None,
            participant_id=None,
            action_id=None,
            sequence=event_sequence,
            event_type=RESULT_PUBLISHED_EVENT_TYPE,
            payload={
                "results": [
                    {
                        "participant": {
                            "display_name": result.display_name,
                            "seat_number": result.seat_number,
                            "revealed_participant_type": result.revealed_participant_type,
                        },
                        "final_score": result.final_score,
                        "rank": result.rank,
                        "is_winner": result.is_winner,
                        "vote_score_delta": result.vote_score_delta,
                    }
                    for result in results
                ]
            },
            created_at=now,
        )
        self.db_session.add(event)
        return event

    async def flush(self) -> None:
        """현재 session의 pending 변경을 DB에 반영해 row id와 제약을 확정합니다."""
        await self.db_session.flush()

    async def commit(self) -> None:
        """투표 상태 변경 transaction을 확정합니다."""
        await self.db_session.commit()
