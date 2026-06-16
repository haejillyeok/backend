from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.be.services.game.records.game_session_participant_record import (
    GameSessionParticipantRecord,
)
from app.be.services.game.records.game_session_turn_record import GameSessionTurnRecord
from app.be.services.game.records.rule_defaults import default_room_rule_config


@dataclass(frozen=True)
class GameSessionStartResult:
    game_session_public_id: UUID
    room_public_id: UUID
    game_type: str
    status: str
    participants: list[GameSessionParticipantRecord]
    rule_config: dict[str, int] = field(default_factory=default_room_rule_config)
    game_session_token: str = ""
    game_session_token_expires_at: datetime | None = None
    current_turn: GameSessionTurnRecord | None = None
