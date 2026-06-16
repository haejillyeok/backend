from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CurrentLobbyMembership:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int
    is_owner: bool
    lobby_websocket_path: str
