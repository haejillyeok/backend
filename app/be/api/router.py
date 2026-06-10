from fastapi import APIRouter

from app.be.api.endpoints.auth import router as auth_router
from app.be.api.endpoints.health import api_router as health_router
from app.be.api.endpoints.realtime_ws import router as realtime_ws_router
from app.be.api.endpoints.ws_docs import router as ws_docs_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(realtime_ws_router)
router.include_router(ws_docs_router)
