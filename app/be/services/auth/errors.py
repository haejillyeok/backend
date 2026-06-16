from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


class SessionExpiredError(AppException):
    """세션 쿠키가 없거나 만료/폐기된 세션일 때 발생합니다."""

    def __init__(self, *, message: str | None = None) -> None:
        super().__init__(code=ErrorCode.SESSION_EXPIRED, message=message)
