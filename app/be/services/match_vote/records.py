from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


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
