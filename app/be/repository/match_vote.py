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
from app.be.schemas.game_enum import GameSessionStatus, RoomStatus
from app.be.services.match_vote import (
    MatchResultParticipantPayload,
    VoteAcceptedRecord,
    VoteSubmissionRecord,
)
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException
from app.shared.core.identifiers import generate_uuid_v7


VOTE_SUBMIT_ACTION_TYPE = "vote_submit"
VOTE_ACCEPTED_EVENT_TYPE = "vote.accepted"
VOTE_TIMEOUT_EVENT_TYPE = "vote.timeout"
RESULT_PUBLISHED_EVENT_TYPE = "result.published"


class MatchVoteRepository:
    """AI 지목 투표와 결과 확정 상태 변경을 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def record_vote_submission(
        self,
        *,
        game_session_public_id: UUID,
        voter_participant_id: UUID,
        target_seat_number: int,
        now: datetime,
    ) -> VoteSubmissionRecord:
        """투표 제출을 저장하고 모든 실제 유저 투표 완료 시 결과를 확정합니다."""
        game_session = await self._get_game_session(game_session_public_id)
        if game_session.status != GameSessionStatus.VOTING.value:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "game_session_not_voting"},
            )
        await self._ensure_voting_deadline_not_exceeded(game_session=game_session, now=now)
        voter = await self._get_participant(
            session_id=game_session.id,
            participant_id=voter_participant_id,
        )
        target = await self._get_participant_by_seat_number(
            session_id=game_session.id,
            seat_number=target_seat_number,
        )
        if voter.participant_type != "user":
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "only_user_can_vote"},
            )

        participants = await self._list_participants(game_session.id)
        existing_votes = await self._list_votes(game_session.id)
        if any(vote.voter_participant_id == voter.id for vote in existing_votes):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "vote_already_submitted"},
            )

        base_scores = await self._score_totals(game_session.id)
        is_correct = target.is_uninvited_guest is True
        action_number = await self._next_action_number(game_session.id)
        action = ParticipantAction(
            id=generate_uuid_v7(),
            session_id=game_session.id,
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
        vote = Vote(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            voter_participant_id=voter.id,
            target_participant_id=target.id,
            voted_at=now,
            is_correct=is_correct,
        )
        self.db_session.add(action)
        self.db_session.add(vote)
        await self.db_session.flush()

        submitted_vote_count = len(existing_votes) + 1
        required_vote_count = len(
            [participant for participant in participants if participant.participant_type == "user"]
        )
        accepted_sequence = await self._next_event_sequence(game_session.id)
        accepted_event = GameEvent(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_id=None,
            participant_id=voter.id,
            action_id=action.id,
            sequence=accepted_sequence,
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
        self.db_session.add(accepted_event)

        all_votes = [*existing_votes, vote]
        result_records: list[MatchResultParticipantPayload] | None = None
        result_event_sequence: int | None = None
        if submitted_vote_count >= required_vote_count:
            result_event_sequence = accepted_sequence + 1
            result_records = await self._publish_results(
                game_session=game_session,
                participants=participants,
                votes=all_votes,
                base_scores=base_scores,
                event_sequence=result_event_sequence,
                now=now,
            )

        await self.db_session.flush()
        return VoteSubmissionRecord(
            accepted=VoteAcceptedRecord(
                game_session_public_id=game_session.public_id,
                event_sequence=accepted_event.sequence,
                voter_display_name=voter.display_name,
                voter_seat_number=voter.seat_number,
                submitted_vote_count=submitted_vote_count,
                required_vote_count=required_vote_count,
                created_at=now,
            ),
            result=result_records,
            result_event_sequence=result_event_sequence,
            result_created_at=now if result_records is not None else None,
        )

    async def commit(self) -> None:
        """투표 상태 변경 transaction을 확정합니다."""
        await self.db_session.commit()

    async def publish_result_for_timeout(
        self,
        *,
        game_session_public_id: UUID,
        now: datetime,
    ) -> VoteSubmissionRecord | None:
        """투표 deadline 초과 시 제출된 투표만 반영해 결과를 확정합니다."""
        game_session = await self._get_game_session(game_session_public_id)
        if game_session.status == GameSessionStatus.RESULT.value:
            return None
        if game_session.status != GameSessionStatus.VOTING.value:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "game_session_not_voting"},
            )
        participants = await self._list_participants(game_session.id)
        votes = await self._list_votes(game_session.id)
        base_scores = await self._score_totals(game_session.id)
        submitted_vote_count = len(votes)
        required_vote_count = len(
            [participant for participant in participants if participant.participant_type == "user"]
        )
        timeout_sequence = await self._next_event_sequence(game_session.id)
        timeout_event = GameEvent(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_id=None,
            participant_id=None,
            action_id=None,
            sequence=timeout_sequence,
            event_type=VOTE_TIMEOUT_EVENT_TYPE,
            payload={
                "submitted_vote_count": submitted_vote_count,
                "required_vote_count": required_vote_count,
            },
            created_at=now,
        )
        self.db_session.add(timeout_event)
        result_event_sequence = timeout_sequence + 1
        result_records = await self._publish_results(
            game_session=game_session,
            participants=participants,
            votes=votes,
            base_scores=base_scores,
            event_sequence=result_event_sequence,
            now=now,
        )
        await self.db_session.flush()
        return VoteSubmissionRecord(
            accepted=VoteAcceptedRecord(
                game_session_public_id=game_session.public_id,
                event_sequence=timeout_event.sequence,
                voter_display_name="",
                voter_seat_number=0,
                submitted_vote_count=submitted_vote_count,
                required_vote_count=required_vote_count,
                created_at=now,
            ),
            result=result_records,
            result_event_sequence=result_event_sequence,
            result_created_at=now,
        )

    async def _publish_results(
        self,
        *,
        game_session: GameSession,
        participants: list[SessionParticipant],
        votes: list[Vote],
        base_scores: dict[UUID, int],
        event_sequence: int,
        now: datetime,
    ) -> list[MatchResultParticipantPayload]:
        """투표 점수, 최종 순위, 결과 event를 생성합니다."""
        participants_by_id = {participant.id: participant for participant in participants}
        vote_deltas = {participant.id: 0 for participant in participants}
        for vote in votes:
            voter_delta = 10 if vote.is_correct else -5
            vote_deltas[vote.voter_participant_id] = (
                vote_deltas.get(vote.voter_participant_id, 0) + voter_delta
            )
            target = participants_by_id.get(vote.target_participant_id)
            if target is not None and target.is_uninvited_guest:
                vote_deltas[target.id] = vote_deltas.get(target.id, 0) - 5

        final_scores = {
            participant.id: base_scores.get(participant.id, 0) + vote_deltas.get(participant.id, 0)
            for participant in participants
        }
        ranks = self._rank_by_score(final_scores)
        max_score = max(final_scores.values()) if final_scores else 0
        result_records = [
            MatchResultParticipantPayload(
                display_name=participant.display_name,
                seat_number=participant.seat_number,
                final_score=final_scores[participant.id],
                rank=ranks[participant.id],
                is_winner=final_scores[participant.id] == max_score,
                revealed_participant_type=participant.participant_type,
                vote_score_delta=vote_deltas.get(participant.id, 0),
            )
            for participant in sorted(participants, key=lambda item: item.seat_number)
        ]

        for vote in votes:
            voter_delta = 10 if vote.is_correct else -5
            self.db_session.add(
                ScoreLedger(
                    id=generate_uuid_v7(),
                    session_id=game_session.id,
                    participant_id=vote.voter_participant_id,
                    source_type="vote",
                    source_id=vote.id,
                    reason="vote_correct" if vote.is_correct else "vote_wrong",
                    score_delta=voter_delta,
                    created_at=now,
                )
            )
            target = participants_by_id.get(vote.target_participant_id)
            if target is not None and target.is_uninvited_guest:
                self.db_session.add(
                    ScoreLedger(
                        id=generate_uuid_v7(),
                        session_id=game_session.id,
                        participant_id=target.id,
                        source_type="vote",
                        source_id=vote.id,
                        reason="voted_as_ai",
                        score_delta=-5,
                        created_at=now,
                    )
                )

        for result in result_records:
            participant = next(
                item for item in participants if item.seat_number == result.seat_number
            )
            self.db_session.add(
                SessionResult(
                    id=generate_uuid_v7(),
                    session_id=game_session.id,
                    participant_id=participant.id,
                    final_score=result.final_score,
                    rank=result.rank,
                    is_winner=result.is_winner,
                    revealed_participant_type=result.revealed_participant_type,
                    result_payload={"vote_score_delta": result.vote_score_delta},
                    created_at=now,
                )
            )

        game_session.status = GameSessionStatus.RESULT.value
        game_session.ended_at = now
        room = await self._get_room_for_update(game_session.room_id)
        room.status = RoomStatus.WAITING.value
        room.updated_at = now
        self.db_session.add(
            GameEvent(
                id=generate_uuid_v7(),
                session_id=game_session.id,
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
                        for result in result_records
                    ]
                },
                created_at=now,
            )
        )
        return result_records

    async def _get_room_for_update(self, room_id: UUID) -> Room:
        """결과 확정 후 같은 객실에서 다음 세션을 시작할 수 있도록 room row를 잠그고 조회합니다."""
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

    def _rank_by_score(self, final_scores: dict[UUID, int]) -> dict[UUID, int]:
        """동점자는 같은 등수로 계산합니다."""
        ranked_items = sorted(final_scores.items(), key=lambda item: item[1], reverse=True)
        ranks: dict[UUID, int] = {}
        previous_score: int | None = None
        previous_rank = 0
        for index, (participant_id, score) in enumerate(ranked_items, start=1):
            if previous_score is None or score != previous_score:
                previous_rank = index
                previous_score = score
            ranks[participant_id] = previous_rank
        return ranks

    async def _get_game_session(self, game_session_public_id: UUID) -> GameSession:
        result = await self.db_session.execute(
            select(GameSession)
            .where(GameSession.public_id == game_session_public_id)
            .with_for_update()
        )
        game_session = result.scalar_one_or_none()
        if game_session is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "game_session_not_found"},
            )
        return game_session

    async def _get_participant(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
    ) -> SessionParticipant:
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

    async def _get_participant_by_seat_number(
        self,
        *,
        session_id: UUID,
        seat_number: int,
    ) -> SessionParticipant:
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

    async def _list_participants(self, session_id: UUID) -> list[SessionParticipant]:
        result = await self.db_session.execute(
            select(SessionParticipant)
            .where(SessionParticipant.session_id == session_id)
            .order_by(SessionParticipant.seat_number.asc())
        )
        return list(result.scalars().all())

    async def _list_votes(self, session_id: UUID) -> list[Vote]:
        result = await self.db_session.execute(select(Vote).where(Vote.session_id == session_id))
        return list(result.scalars().all())

    async def _score_totals(self, session_id: UUID) -> dict[UUID, int]:
        result = await self.db_session.execute(
            select(ScoreLedger.participant_id, func.coalesce(func.sum(ScoreLedger.score_delta), 0))
            .where(ScoreLedger.session_id == session_id)
            .group_by(ScoreLedger.participant_id)
        )
        return {participant_id: int(score or 0) for participant_id, score in result.all()}

    async def _ensure_voting_deadline_not_exceeded(
        self,
        *,
        game_session: GameSession,
        now: datetime,
    ) -> None:
        """투표 phase deadline 이후 제출된 vote command는 저장하지 않고 timeout 확정으로 넘깁니다."""
        if game_session.current_phase_id is None:
            return
        result = await self.db_session.execute(
            select(SessionPhase).where(
                SessionPhase.id == game_session.current_phase_id,
                SessionPhase.session_id == game_session.id,
                SessionPhase.phase_type == "voting",
            )
        )
        voting_phase = result.scalar_one_or_none()
        if voting_phase is None or voting_phase.deadline_at is None:
            return
        if now >= voting_phase.deadline_at:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "vote_deadline_exceeded"},
            )

    async def _next_action_number(self, session_id: UUID) -> int:
        result = await self.db_session.execute(
            select(func.coalesce(func.max(ParticipantAction.action_number), 0)).where(
                ParticipantAction.session_id == session_id
            )
        )
        return int(result.scalar_one()) + 1

    async def _next_event_sequence(self, session_id: UUID) -> int:
        result = await self.db_session.execute(
            select(func.coalesce(func.max(GameEvent.sequence), 0)).where(
                GameEvent.session_id == session_id
            )
        )
        return int(result.scalar_one()) + 1
