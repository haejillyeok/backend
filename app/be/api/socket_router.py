from fastapi import APIRouter

from app.be.api.endpoints.lobby_ws import router as lobby_ws_router
from app.be.api.endpoints.match_ws import router as match_ws_router
from app.be.api.endpoints.realtime_ws import router as realtime_ws_router


socket_router = APIRouter()
socket_router.include_router(lobby_ws_router)
socket_router.include_router(match_ws_router)
socket_router.include_router(realtime_ws_router)
