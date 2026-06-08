from typing import Any

from app.shared.core.error_codes import ErrorCode, ErrorType, get_error_definition


class AppException(Exception):
    """HTTP/WebSocket handler가 변환할 수 있는 공통 애플리케이션 예외입니다."""

    def __init__(
        self,
        *,
        code: ErrorCode | str,
        message: str | None = None,
        details: Any | None = None,
        http_status_code: int | None = None,
        websocket_close_code: int | None = None,
        error_type: ErrorType | None = None,
    ) -> None:
        definition = get_error_definition(code) if isinstance(code, ErrorCode) else None
        resolved_message = message or (definition.message if definition else str(code))
        super().__init__(resolved_message)
        self.code = code.value if isinstance(code, ErrorCode) else code
        self.error_type = error_type or (definition.type if definition else ErrorType.INTERNAL)
        self.message = resolved_message
        self.details = details
        self.http_status_code = (
            http_status_code
            if http_status_code is not None
            else definition.http_status_code
            if definition
            else 500
        )
        self.websocket_close_code = (
            websocket_close_code
            if websocket_close_code is not None
            else definition.websocket_close_code
            if definition
            else 1011
        )

    def to_error_payload(self) -> dict[str, Any]:
        """HTTP/WebSocket 등 JSON 경계에서 사용할 공통 error payload를 반환합니다."""
        return {
            "success": False,
            "data": None,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


class InvalidCredentialsError(AppException):
    """닉네임은 존재하지만 비밀번호가 일치하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(
            code=ErrorCode.INVALID_CREDENTIALS,
        )
