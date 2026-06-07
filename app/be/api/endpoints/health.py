from fastapi import APIRouter

from app.be.schemas.response.health import HealthResponse
from app.shared.core.responses import SuccessResponse, ok

router = APIRouter(tags=["be-health"])
api_router = APIRouter(tags=["be-health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="BE 루트 헬스 체크",
    operation_id="be_root_health_check",
)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@api_router.get(
    "/health",
    response_model=SuccessResponse[HealthResponse],
    summary="BE API 헬스 체크",
    operation_id="be_api_health_check",
)
def api_health_check() -> SuccessResponse[HealthResponse]:
    """API 클라이언트용 공통 응답 envelope로 서비스 상태를 반환합니다."""
    return ok(HealthResponse(status="ok"))
