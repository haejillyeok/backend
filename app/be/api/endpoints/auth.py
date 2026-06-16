from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.be.api.endpoints.auth_cookies import (
    set_session_cookie,
    settings,
)
from app.be.api.endpoints.auth_mappers import map_login_response, map_signup_response
from app.be.dependencies.services import get_auth_service
from app.be.schemas.request.auth import LoginRequest, SignupRequest
from app.be.schemas.response.auth import LoginResponse, SignupResponse
from app.be.services.auth import AuthService
from app.shared.core.client_ip import resolve_best_effort_client_ip
from app.shared.core.error_codes import ErrorCode
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok


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
    return ok(map_login_response(result))


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
    return ok(map_signup_response(result))


def _set_session_cookie(
    response: Response,
    *,
    session_token: str,
    expires_at: datetime,
) -> None:
    """기존 테스트/호출자가 쓰던 세션 쿠키 helper 경로를 유지합니다."""
    set_session_cookie(
        response,
        session_token=session_token,
        expires_at=expires_at,
        app_settings=settings,
    )
