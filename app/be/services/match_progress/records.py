from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class AiAnswerFailureRecord:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    display_name: str
    seat_number: int
    action_id: UUID
    event_id: UUID
    event_sequence: int
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    next_turn: MatchTurnEventPayload | None = None
    next_status: str | None = None
    voting_deadline_at: datetime | None = None


@dataclass(frozen=True)
class TurnTimeoutRecord:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    display_name: str
    seat_number: int
    action_id: UUID
    event_id: UUID
    event_sequence: int
    deadline_at: datetime
    created_at: datetime
    round_number: int | None = None
    next_turn: MatchTurnEventPayload | None = None
    next_status: str | None = None
    voting_deadline_at: datetime | None = None


@dataclass(frozen=True)
class MatchTurnEventPayload:
    phase_id: UUID
    round_number: int
    turn_number: int
    actor_seat_number: int
    started_at: datetime
    deadline_at: datetime
    required_start_char: str | None


@dataclass(frozen=True)
class WordSubmissionRecord:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    display_name: str
    seat_number: int
    word: str
    normalized_word: str
    action_id: UUID
    submission_id: UUID
    event_id: UUID
    event_sequence: int
    score_delta: int
    next_turn: MatchTurnEventPayload
    created_at: datetime


@dataclass(frozen=True)
class WordRejectionRecord:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    display_name: str
    seat_number: int
    word: str
    normalized_word: str
    action_id: UUID
    event_id: UUID
    event_sequence: int
    reason: str
    details: dict[str, Any]
    score_delta: int
    created_at: datetime


@dataclass(frozen=True)
class MatchBroadcastEvent:
    game_session_public_id: UUID
    message: dict[str, Any]
