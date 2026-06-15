from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.be.services.match_progress import MatchBroadcastEvent


VOTE_ACCEPTED_MESSAGE_TYPE = "match.vote.accepted"
VOTE_TIMEOUT_MESSAGE_TYPE = "match.vote.timeout"
RESULT_PUBLISHED_MESSAGE_TYPE = "match.result.published"


@dataclass(frozen=True)
class VoteAcceptedRecord:
    game_session_public_id: UUID
    event_sequence: int
    voter_display_name: str
    voter_seat_number: int
    submitted_vote_count: int
    required_vote_count: int
    created_at: datetime


@dataclass(frozen=True)
class MatchResultParticipantPayload:
    display_name: str
    seat_number: int
    final_score: int
    rank: int
    is_winner: bool
    revealed_participant_type: str
    vote_score_delta: int


@dataclass(frozen=True)
class VoteSubmissionRecord:
    accepted: VoteAcceptedRecord
    result: list[MatchResultParticipantPayload] | None
    result_event_sequence: int | None = None
    result_created_at: datetime | None = None


class MatchVoteRepositoryProtocol(Protocol):
    async def record_vote_submission(
        self,
        *,
        game_session_public_id: UUID,
        voter_participant_id: UUID,
        target_seat_number: int,
        now: datetime,
    ) -> VoteSubmissionRecord:
        """투표 제출을 저장하고 결과 확정 여부를 포함한 record를 반환합니다."""

    async def publish_result_for_timeout(
        self,
        *,
        game_session_public_id: UUID,
        now: datetime,
    ) -> VoteSubmissionRecord | None:
        """투표 deadline 초과로 결과를 확정하고 record를 반환합니다."""

    async def commit(self) -> None:
        """투표 상태 변경 transaction을 확정합니다."""


class MatchVoteService:
    """투표 제출을 확정하고 match WebSocket broadcast event로 변환합니다."""

    def __init__(self, repository: MatchVoteRepositoryProtocol) -> None:
        self.repository = repository

    async def submit_vote(
        self,
        *,
        game_session_public_id: UUID,
        voter_participant_id: UUID,
        target_seat_number: int,
        now: datetime,
    ) -> list[MatchBroadcastEvent]:
        """AI 지목 투표를 저장하고 commit 이후 전송할 event 목록을 반환합니다."""
        record = await self.repository.record_vote_submission(
            game_session_public_id=game_session_public_id,
            voter_participant_id=voter_participant_id,
            target_seat_number=target_seat_number,
            now=now,
        )
        await self.repository.commit()
        events = [
            MatchBroadcastEvent(
                game_session_public_id=record.accepted.game_session_public_id,
                message={
                    "type": VOTE_ACCEPTED_MESSAGE_TYPE,
                    "payload": {
                        "event_sequence": record.accepted.event_sequence,
                        "voter": {
                            "display_name": record.accepted.voter_display_name,
                            "seat_number": record.accepted.voter_seat_number,
                        },
                        "submitted_vote_count": record.accepted.submitted_vote_count,
                        "required_vote_count": record.accepted.required_vote_count,
                        "created_at": record.accepted.created_at,
                        "server_time": record.accepted.created_at,
                    },
                },
            )
        ]
        if record.result is not None:
            events.append(
                MatchBroadcastEvent(
                    game_session_public_id=record.accepted.game_session_public_id,
                    message={
                        "type": RESULT_PUBLISHED_MESSAGE_TYPE,
                        "payload": {
                            "event_sequence": record.result_event_sequence,
                            "results": [
                                {
                                    "participant": {
                                        "display_name": result.display_name,
                                        "seat_number": result.seat_number,
                                        "revealed_participant_type": (
                                            result.revealed_participant_type
                                        ),
                                    },
                                    "final_score": result.final_score,
                                    "rank": result.rank,
                                    "is_winner": result.is_winner,
                                    "vote_score_delta": result.vote_score_delta,
                                }
                                for result in record.result
                            ],
                            "created_at": record.result_created_at,
                            "server_time": record.result_created_at,
                        },
                    },
                )
            )
        return events

    async def timeout_vote(
        self,
        *,
        game_session_public_id: UUID,
        now: datetime,
    ) -> list[MatchBroadcastEvent]:
        """투표 deadline 초과를 확정하고 결과 broadcast event를 반환합니다."""
        record = await self.repository.publish_result_for_timeout(
            game_session_public_id=game_session_public_id,
            now=now,
        )
        if record is None:
            return []
        await self.repository.commit()
        events = [
            MatchBroadcastEvent(
                game_session_public_id=record.accepted.game_session_public_id,
                message={
                    "type": VOTE_TIMEOUT_MESSAGE_TYPE,
                    "payload": {
                        "event_sequence": record.accepted.event_sequence,
                        "submitted_vote_count": record.accepted.submitted_vote_count,
                        "required_vote_count": record.accepted.required_vote_count,
                        "created_at": record.accepted.created_at,
                        "server_time": record.accepted.created_at,
                    },
                },
            )
        ]
        if record.result is not None:
            events.append(self._result_event(record))
        return events

    def _result_event(self, record: VoteSubmissionRecord) -> MatchBroadcastEvent:
        """결과 record를 WebSocket event payload로 변환합니다."""
        return MatchBroadcastEvent(
            game_session_public_id=record.accepted.game_session_public_id,
            message={
                "type": RESULT_PUBLISHED_MESSAGE_TYPE,
                "payload": {
                    "event_sequence": record.result_event_sequence,
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
                        for result in record.result or []
                    ],
                    "created_at": record.result_created_at,
                    "server_time": record.result_created_at,
                },
            },
        )
