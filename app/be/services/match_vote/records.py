from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ScoreBreakdownItem:
    reason: str
    score_delta: int


@dataclass(frozen=True)
class ScoreBreakdownPayload:
    word_score: int
    vote_score: int
    penalty_score: int
    items: list[ScoreBreakdownItem] = field(default_factory=list)


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
    score_breakdown: ScoreBreakdownPayload = field(
        default_factory=lambda: ScoreBreakdownPayload(
            word_score=0,
            vote_score=0,
            penalty_score=0,
        )
    )


@dataclass(frozen=True)
class VoteSubmissionRecord:
    accepted: VoteAcceptedRecord
    result: list[MatchResultParticipantPayload] | None
    result_event_sequence: int | None = None
    result_created_at: datetime | None = None
