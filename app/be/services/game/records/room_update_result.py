from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RoomUpdateResult:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    rule_config: dict[str, int]
