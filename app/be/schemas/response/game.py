from uuid import UUID

from app.be.schemas.base import SchemaModel


class GameSessionParticipantResponse(SchemaModel):
    participant_type: str
    display_name: str
    seat_number: int
    is_uninvited_guest: bool


class StartGameSessionResponse(SchemaModel):
    session_public_id: UUID
    room_public_id: UUID
    game_type: str
    status: str
    participants: list[GameSessionParticipantResponse]


class GameSessionEntryResponse(SchemaModel):
    session_public_id: UUID
    allowed: bool
    participant: GameSessionParticipantResponse
