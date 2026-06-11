from fastapi import APIRouter, Depends

from app.agent.api.endpoints import answer, data_stack
from app.agent.api.endpoints.health import router as health_router
from app.agent.core.security import require_agent_api_key

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(
    answer.router,
    dependencies=[Depends(require_agent_api_key)],
)
router.include_router(
    data_stack.router,
    dependencies=[Depends(require_agent_api_key)],
)
