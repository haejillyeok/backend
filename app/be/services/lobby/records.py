from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.be.services.auth import CurrentUser


LobbyMessage = dict[str, Any]


@dataclass(frozen=True)
class LobbyConnection:
    user: CurrentUser
    room_public_id: UUID
    last_seen_at: datetime


@dataclass(frozen=True)
class LobbyDisconnect:
    user: CurrentUser
    room_public_id: UUID


GraceLeaveCallback = Callable[[LobbyDisconnect], Awaitable[None]]
