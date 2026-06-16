from dataclasses import dataclass
from uuid import UUID

from app.be.services.game import GameSessionParticipantRecord


@dataclass(frozen=True)
class MatchConnection:
    game_session_public_id: UUID
    participant_id: UUID
    participant: GameSessionParticipantRecord
