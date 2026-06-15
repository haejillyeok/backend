from datetime import datetime
from uuid import UUID

from app.be.schemas.base import SchemaModel
from app.be.schemas.game_enum import GameSessionStatus, GameType, RoomStatus


class GameRoomSummaryResponse(SchemaModel):
    room_public_id: UUID
    name: str
    game_type: GameType
    status: RoomStatus
    max_players: int
    member_count: int
    is_current_user_member: bool
    is_current_user_owner: bool
    lobby_websocket_path: str


class CurrentLobbyMembershipResponse(SchemaModel):
    room_public_id: UUID
    name: str
    game_type: GameType
    status: RoomStatus
    max_players: int
    member_count: int
    is_owner: bool
    lobby_websocket_path: str


class GameRoomListResponse(SchemaModel):
    rooms: list[GameRoomSummaryResponse]
    current_membership: CurrentLobbyMembershipResponse | None


class CreateGameRoomResponse(SchemaModel):
    room_public_id: UUID
    name: str
    game_type: GameType
    status: RoomStatus
    max_players: int
    member_count: int
    created_at: datetime


class GameRoomRuleConfigResponse(SchemaModel):
    max_rounds: int
    turn_time_seconds: int


class UpdateGameRoomResponse(SchemaModel):
    room_public_id: UUID
    name: str
    game_type: GameType
    status: RoomStatus
    max_players: int
    rule_config: GameRoomRuleConfigResponse


class RoomJoinResponse(SchemaModel):
    room_public_id: UUID
    user_public_id: UUID
    nickname: str
    joined_at: datetime
    already_member: bool


class RoomLeaveResponse(SchemaModel):
    room_public_id: UUID
    user_public_id: UUID
    nickname: str
    left_at: datetime
    remaining_member_count: int
    new_owner_user_public_id: UUID | None
    new_owner_nickname: str | None
    room_closed: bool


class GameSessionParticipantResponse(SchemaModel):
    display_name: str
    seat_number: int


class GameSessionTurnResponse(SchemaModel):
    phase_id: UUID
    round_number: int
    turn_number: int
    actor_seat_number: int
    deadline_at: datetime | None
    required_start_char: str | None


class StartGameSessionResponse(SchemaModel):
    game_session_public_id: UUID
    room_public_id: UUID
    game_type: GameType
    status: GameSessionStatus
    game_session_token: str
    game_session_token_expires_at: datetime
    rule_config: GameRoomRuleConfigResponse
    current_turn: GameSessionTurnResponse | None
    participants: list[GameSessionParticipantResponse]


class GameSessionEntryResponse(SchemaModel):
    game_session_public_id: UUID
    allowed: bool
    game_session_token: str
    game_session_token_expires_at: datetime
    participant: GameSessionParticipantResponse
