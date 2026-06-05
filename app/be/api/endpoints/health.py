from fastapi import APIRouter

from app.be.schemas.response.health import HealthResponse
from app.shared.core.responses import ResponseEnvelope, ok

router = APIRouter(tags=["be-health"])
api_router = APIRouter(tags=["be-health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@api_router.get("/health", response_model=ResponseEnvelope[HealthResponse])
def api_health_check() -> ResponseEnvelope[HealthResponse]:
    """API 클라이언트용 공통 응답 envelope로 서비스 상태를 반환합니다."""
    return ok(HealthResponse(status="ok"))
