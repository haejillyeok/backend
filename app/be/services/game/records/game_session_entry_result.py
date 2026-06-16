from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.be.services.game.records.game_session_participant_record import (
    GameSessionParticipantRecord,
)


@dataclass(frozen=True)
class GameSessionEntryResult:
    game_session_public_id: UUID
    participant: GameSessionParticipantRecord
    game_session_token: str
    game_session_token_expires_at: datetime
    allowed: bool = True
