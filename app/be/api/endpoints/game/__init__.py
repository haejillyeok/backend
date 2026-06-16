from fastapi import APIRouter

from app.be.api.endpoints.game.entries import router as entries_router
from app.be.api.endpoints.game.mappers import (
    map_entry_result,
    map_room_create_result,
    map_room_join_result,
    map_room_leave_result,
    map_room_list_item,
    map_room_update_result,
    map_start_result,
)
from app.be.api.endpoints.game.rooms import router as rooms_router
from app.be.api.endpoints.game.sessions import router as sessions_router
from app.be.services.lobby import lobby_connection_manager
from app.shared.core.timezone import kst_now


router = APIRouter(prefix="/game", tags=["game"])
router.include_router(rooms_router)
router.include_router(sessions_router)
router.include_router(entries_router)

__all__ = [
    "kst_now",
    "lobby_connection_manager",
    "map_entry_result",
    "map_room_create_result",
    "map_room_join_result",
    "map_room_leave_result",
    "map_room_list_item",
    "map_room_update_result",
    "map_start_result",
    "router",
]
