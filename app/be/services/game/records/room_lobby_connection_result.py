from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.be.services.game.records.room_lobby_snapshot_result import RoomLobbySnapshotResult


@dataclass(frozen=True)
class RoomLobbyConnectionResult:
    room_public_id: UUID
    snapshot: RoomLobbySnapshotResult | None = None
