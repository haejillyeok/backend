from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.be.dependencies.services import get_auth_service
from app.be.schemas.request.auth import LoginRequest, SignupRequest
from app.be.schemas.response.auth import AuthUserResponse, LoginResponse, SignupResponse
from app.be.services.auth import AuthService
from app.shared.core.client_ip import resolve_best_effort_client_ip
from app.shared.core.config import AppSettings
from app.shared.core.error_codes import ErrorCode
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok


SESSION_COOKIE_NAME = "session_token"
settings = AppSettings(app_name="haejillyeok-be")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=SuccessResponse[LoginResponse],
    status_code=status.HTTP_200_OK,
    summary="로그인",
    operation_id="be_auth_login",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.INVALID_CREDENTIALS,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessResponse[LoginResponse]:
    """계정 ID/비밀번호로 기존 계정을 인증하고 세션 쿠키를 발급합니다."""
    result = await auth_service.login(
        account_id=payload.account_id,
        password=payload.password,
        last_access_ip=resolve_best_effort_client_ip(
            request.headers,
            peer_host=request.client.host if request.client else None,
        ),
        user_agent=request.headers.get("user-agent"),
    )

    _set_session_cookie(response, session_token=result.session_token, expires_at=result.expires_at)
    return ok(
        LoginResponse(
            user=AuthUserResponse(
                public_id=result.user.public_id,
                account_id=result.user.account_id,
                nickname=result.user.nickname,
            ),
            expires_at=result.expires_at,
        ),
    )


@router.post(
    "/signup",
    response_model=SuccessResponse[SignupResponse],
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    operation_id="be_auth_signup",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.AUTH_USER_CONFLICT,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> SuccessResponse[SignupResponse]:
    """계정 ID/닉네임/비밀번호로 신규 계정을 만들고 세션 쿠키를 발급합니다."""
    result = await auth_service.signup(
        account_id=payload.account_id,
        nickname=payload.nickname,
        password=payload.password,
        last_access_ip=resolve_best_effort_client_ip(
            request.headers,
            peer_host=request.client.host if request.client else None,
        ),
        user_agent=request.headers.get("user-agent"),
    )

    _set_session_cookie(response, session_token=result.session_token, expires_at=result.expires_at)
    return ok(
        SignupResponse(
            user=AuthUserResponse(
                public_id=result.user.public_id,
                account_id=result.user.account_id,
                nickname=result.user.nickname,
            ),
            expires_at=result.expires_at,
        ),
    )


def _set_session_cookie(
    response: Response,
    *,
    session_token: str,
    expires_at: datetime,
) -> None:
    """로그인/회원가입 성공 시 공통 세션 쿠키 속성을 적용합니다."""
    cookie_expires_at = expires_at.astimezone(UTC)
    is_prod = settings.environment == "prod"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        # HTTP cookie Expires는 GMT 형식만 허용하므로 저장/응답 시간 기준과 별도로 변환합니다.
        expires=cookie_expires_at,
        httponly=True,
        secure=is_prod,
        # 로컬 테스트는 HTTP라 Lax를 유지하고, 운영 API는 localhost 테스트 페이지 같은 cross-site
        # credential 요청에서도 쿠키가 전송되도록 None+Secure 조합을 사용합니다.
        samesite="none" if is_prod else "lax",
    )
