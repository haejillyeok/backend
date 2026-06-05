from fastapi import APIRouter

from app.be.schemas.response.health import HealthResponse

router = APIRouter(tags=["be-health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
