from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class GameSessionParticipantRecord:
    participant_id: UUID | None
    game_session_public_id: UUID
    user_id: UUID | None
    participant_type: str
    display_name: str
    seat_number: int
    is_uninvited_guest: bool
    original_nickname: str | None = None
    resume_token_expires_at: datetime | None = None
