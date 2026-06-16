from fastapi import APIRouter

from app.be.api.endpoints.game.room_listing_routes import router as listing_router
from app.be.api.endpoints.game.room_membership_routes import router as membership_router
from app.be.api.endpoints.game.room_settings_routes import router as settings_router


router = APIRouter()
router.include_router(listing_router)
router.include_router(settings_router)
router.include_router(membership_router)
