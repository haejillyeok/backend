from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.be.services.game.records.rule_defaults import default_room_rule_config


@dataclass(frozen=True)
class GameRoomRecord:
    id: UUID
    public_id: UUID
    owner_user_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    rule_config: dict[str, int] = field(default_factory=default_room_rule_config)
    created_at: datetime | None = None
