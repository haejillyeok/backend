from fastapi import APIRouter

from app.be.api.endpoints.agent import router as agent_router
from app.be.api.endpoints.auth import router as auth_router
from app.be.api.endpoints.health import api_router as health_router

router = APIRouter(prefix="/api/v1")
router.include_router(agent_router)
router.include_router(auth_router)
router.include_router(health_router)
