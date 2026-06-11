from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    """프로토콜 경계에서 클라이언트에 노출하는 공통 에러 코드입니다."""

    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    HTTP_ERROR = "HTTP_ERROR"
    AGENT_CLIENT_NOT_CONFIGURED = "AGENT_CLIENT_NOT_CONFIGURED"
    AGENT_HEALTH_UNAVAILABLE = "AGENT_HEALTH_UNAVAILABLE"


class ErrorType(StrEnum):
    """에러 코드의 업무/프로토콜 분류입니다."""

    VALIDATION = "VALIDATION"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    INTERNAL = "INTERNAL"


@dataclass(frozen=True)
class ErrorDefinition:
    """HTTP와 WebSocket에서 공통으로 사용할 에러 코드 정의입니다."""

    code: ErrorCode
    type: ErrorType
    message: str
    http_status_code: int
    websocket_close_code: int

    @property
    def example_name(self) -> str:
        """Swagger examples key에 사용할 안정적인 snake_case 이름입니다."""
        return self.code.value.lower()

    @property
    def summary(self) -> str:
        """Swagger example 제목으로 사용할 짧은 설명입니다."""
        return self.message


ERROR_TYPE_DESCRIPTIONS: dict[ErrorType, str] = {
    ErrorType.VALIDATION: "Validation errors",
    ErrorType.AUTHENTICATION: "Authentication errors",
    ErrorType.AUTHORIZATION: "Authorization errors",
    ErrorType.NOT_FOUND: "Not found errors",
    ErrorType.CONFLICT: "Conflict errors",
    ErrorType.INTERNAL: "Internal errors",
}


ERROR_DEFINITIONS: dict[ErrorCode, ErrorDefinition] = {
    ErrorCode.INVALID_CREDENTIALS: ErrorDefinition(
        code=ErrorCode.INVALID_CREDENTIALS,
        type=ErrorType.AUTHENTICATION,
        message="계정 ID 또는 비밀번호가 올바르지 않습니다.",
        http_status_code=401,
        websocket_close_code=1008,
    ),
    ErrorCode.SESSION_EXPIRED: ErrorDefinition(
        code=ErrorCode.SESSION_EXPIRED,
        type=ErrorType.AUTHENTICATION,
        message="세션이 만료되었습니다.",
        http_status_code=401,
        websocket_close_code=1008,
    ),
    ErrorCode.VALIDATION_ERROR: ErrorDefinition(
        code=ErrorCode.VALIDATION_ERROR,
        type=ErrorType.VALIDATION,
        message="요청 값이 올바르지 않습니다.",
        http_status_code=422,
        websocket_close_code=1008,
    ),
    ErrorCode.HTTP_ERROR: ErrorDefinition(
        code=ErrorCode.HTTP_ERROR,
        type=ErrorType.INTERNAL,
        message="요청 처리 중 오류가 발생했습니다.",
        http_status_code=500,
        websocket_close_code=1011,
    ),
    ErrorCode.AGENT_CLIENT_NOT_CONFIGURED: ErrorDefinition(
        code=ErrorCode.AGENT_CLIENT_NOT_CONFIGURED,
        type=ErrorType.INTERNAL,
        message="Agent client is not configured.",
        http_status_code=503,
        websocket_close_code=1011,
    ),
    ErrorCode.AGENT_HEALTH_UNAVAILABLE: ErrorDefinition(
        code=ErrorCode.AGENT_HEALTH_UNAVAILABLE,
        type=ErrorType.INTERNAL,
        message="Agent health check failed.",
        http_status_code=502,
        websocket_close_code=1011,
    ),
}


def get_error_definition(code: ErrorCode | str) -> ErrorDefinition:
    """에러 코드의 프로토콜별 매핑 정의를 반환합니다."""
    error_code = code if isinstance(code, ErrorCode) else ErrorCode(code)
    return ERROR_DEFINITIONS[error_code]


def get_error_type_description(error_type: ErrorType) -> str:
    """에러 유형의 Swagger response description을 반환합니다."""
    return ERROR_TYPE_DESCRIPTIONS[error_type]
