from fastapi import APIRouter, Depends

from app.be.api.endpoints.agent import router as agent_router
from app.be.api.endpoints.auth import router as auth_router
from app.be.api.endpoints.game import router as game_router
from app.be.api.endpoints.health import api_router as health_router
from app.be.dependencies.services import get_current_user

router = APIRouter()

public_router = APIRouter(prefix="/api/v1")
public_router.include_router(agent_router)
public_router.include_router(auth_router)
public_router.include_router(health_router)

protected_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(get_current_user)],
)
protected_router.include_router(game_router)

router.include_router(public_router)
router.include_router(protected_router)
