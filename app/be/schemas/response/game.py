from datetime import datetime
from uuid import UUID

from app.be.schemas.base import SchemaModel
from app.be.schemas.game_enum import GameSessionStatus, GameType, ParticipantType, RoomStatus


class GameRoomSummaryResponse(SchemaModel):
    room_public_id: UUID
    name: str
    game_type: GameType
    status: RoomStatus
    max_players: int
    member_count: int


class GameRoomListResponse(SchemaModel):
    rooms: list[GameRoomSummaryResponse]


class CreateGameRoomResponse(SchemaModel):
    room_public_id: UUID
    name: str
    game_type: GameType
    status: RoomStatus
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
    participant_type: ParticipantType
    display_name: str
    seat_number: int
    is_uninvited_guest: bool


class StartGameSessionResponse(SchemaModel):
    game_session_public_id: UUID
    room_public_id: UUID
    game_type: GameType
    status: GameSessionStatus
    game_session_token: str
    game_session_token_expires_at: datetime
    participants: list[GameSessionParticipantResponse]


class GameSessionEntryResponse(SchemaModel):
    game_session_public_id: UUID
    allowed: bool
    game_session_token: str
    game_session_token_expires_at: datetime
    participant: GameSessionParticipantResponse
