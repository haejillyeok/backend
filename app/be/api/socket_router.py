from fastapi import APIRouter

from app.be.api.endpoints.realtime_ws import router as realtime_ws_router


socket_router = APIRouter()
socket_router.include_router(realtime_ws_router)
