from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class MatchParticipantSnapshot:
    display_name: str
    seat_number: int
    is_me: bool


@dataclass(frozen=True)
class MatchTurnSnapshot:
    phase_id: UUID
    round_number: int
    turn_number: int
    actor_seat_number: int
    started_at: datetime
    deadline_at: datetime | None
    required_start_char: str | None


@dataclass(frozen=True)
class MatchTurnTimer:
    phase_id: UUID
    deadline_at: datetime


@dataclass(frozen=True)
class MatchVotingTimer:
    deadline_at: datetime


MatchTimer = MatchTurnTimer | MatchVotingTimer


@dataclass(frozen=True)
class MatchScoreSnapshot:
    display_name: str
    seat_number: int
    score: int
    is_me: bool


@dataclass(frozen=True)
class MatchResultSnapshot:
    display_name: str
    seat_number: int
    revealed_participant_type: str
    final_score: int
    rank: int
    is_winner: bool
    vote_score_delta: int
    is_me: bool


@dataclass(frozen=True)
class MatchSnapshotResult:
    game_session_public_id: UUID
    status: str
    rule_config: dict[str, int]
    participants: list[MatchParticipantSnapshot]
    current_round_number: int | None
    current_turn: MatchTurnSnapshot | None
    used_words: list[str]
    scoreboard: list[MatchScoreSnapshot]
    server_time: datetime
    voting_deadline_at: datetime | None = None
    results: list[MatchResultSnapshot] = field(default_factory=list)
