from datetime import datetime
from uuid import UUID

from app.be.schemas.base import SchemaModel


class GameRoomSummaryResponse(SchemaModel):
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int


class GameRoomListResponse(SchemaModel):
    rooms: list[GameRoomSummaryResponse]


class CreateGameRoomResponse(SchemaModel):
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int
    created_at: datetime


class RoomJoinResponse(SchemaModel):
    room_public_id: UUID
    user_public_id: UUID
    nickname: str
    joined_at: datetime
    already_member: bool


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
