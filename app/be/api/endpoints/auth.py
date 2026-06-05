from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.be.dependencies.services import get_auth_service
from app.be.schemas.request.auth import LoginRequest
from app.be.schemas.response.auth import LoginResponse, LoginUserResponse
from app.be.services.auth import AuthService
from app.shared.core.config import AppSettings
from app.shared.core.responses import ResponseEnvelope, ok


SESSION_COOKIE_NAME = "session_token"
settings = AppSettings(app_name="haejillyeok-be")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ResponseEnvelope[LoginResponse])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ResponseEnvelope[LoginResponse]:
    """닉네임/비밀번호로 가입 겸 로그인을 처리하고 세션 쿠키를 발급합니다."""
    result = await auth_service.login_or_register(
        nickname=payload.nickname,
        password=payload.password,
        last_access_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=result.session_token,
        expires=result.expires_at,
        httponly=True,
        secure=settings.environment == "prod",
        samesite="lax",
    )
    return ok(
        LoginResponse(
            user=LoginUserResponse(
                public_id=result.user.public_id,
                nickname=result.user.nickname,
            ),
            is_new_user=result.is_new_user,
            expires_at=result.expires_at,
        ),
    )
