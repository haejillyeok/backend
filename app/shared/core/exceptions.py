from typing import Any

from grpc import StatusCode


class AppException(Exception):
    """HTTP, gRPC 등 프로토콜 handler가 변환할 수 있는 공통 애플리케이션 예외입니다."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: Any | None = None,
        http_status_code: int = 500,
        grpc_status_code: StatusCode = StatusCode.UNKNOWN,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.http_status_code = http_status_code
        self.grpc_status_code = grpc_status_code


class InvalidCredentialsError(AppException):
    """닉네임은 존재하지만 비밀번호가 일치하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(
            code="INVALID_CREDENTIALS",
            message="닉네임 또는 비밀번호가 올바르지 않습니다.",
            http_status_code=401,
            grpc_status_code=StatusCode.UNAUTHENTICATED,
        )
