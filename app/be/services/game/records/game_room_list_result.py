from __future__ import annotations

from dataclasses import dataclass

from app.be.services.game.records.current_lobby_membership import CurrentLobbyMembership
from app.be.services.game.records.game_room_list_item import GameRoomListItem


@dataclass(frozen=True)
class GameRoomListResult:
    rooms: list[GameRoomListItem]
    current_membership: CurrentLobbyMembership | None = None
