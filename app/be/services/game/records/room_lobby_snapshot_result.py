from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.be.services.game.records.room_lobby_member_snapshot import RoomLobbyMemberSnapshot


@dataclass(frozen=True)
class RoomLobbySnapshotResult:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int
    rule_config: dict[str, int]
    owner_user_public_id: UUID | None
    members: list[RoomLobbyMemberSnapshot]
