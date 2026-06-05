from fastapi import APIRouter

from app.be.api.endpoints.health import router as health_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
