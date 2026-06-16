from datetime import UTC, datetime

from fastapi import Response

from app.shared.core.config import AppSettings


SESSION_COOKIE_NAME = "session_token"
settings = AppSettings(app_name="haejillyeok-be")


def set_session_cookie(
    response: Response,
    *,
    session_token: str,
    expires_at: datetime,
    app_settings: AppSettings | None = None,
) -> None:
    """로그인/회원가입 성공 시 공통 세션 쿠키 속성을 적용합니다.

    HTTP cookie Expires는 GMT 형식만 허용하므로 저장/응답 시간 기준과 별도로 UTC로
    변환합니다. 운영 환경은 cross-site credential 요청을 허용하기 위해 None+Secure
    조합을 사용합니다.
    """
    cookie_settings = app_settings or settings
    cookie_expires_at = expires_at.astimezone(UTC)
    is_prod = cookie_settings.environment == "prod"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        expires=cookie_expires_at,
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
    )
