from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GameRoomListItem:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int
    is_current_user_member: bool = False
    is_current_user_owner: bool = False
