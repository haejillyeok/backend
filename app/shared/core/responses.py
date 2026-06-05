from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict

from app.shared.core.error_codes import ErrorCode


ResponseDataT = TypeVar("ResponseDataT")


class SharedModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorInfo(SharedModel):
    code: str
    message: str
    details: Any | None = None


class ErrorCodeInfo(SharedModel):
    code: ErrorCode
    message: str
    details: Any | None = None


class ErrorResponse(SharedModel):
    success: Literal[False]
    data: None
    error: ErrorCodeInfo


class SuccessResponse(SharedModel, Generic[ResponseDataT]):
    success: Literal[True]
    data: ResponseDataT


class ResponseEnvelope(SharedModel, Generic[ResponseDataT]):
    success: bool
    data: ResponseDataT | None = None
    error: ErrorInfo | None = None


def ok(data: ResponseDataT) -> SuccessResponse[ResponseDataT]:
    """프로토콜 경계에서 사용할 성공 response envelope를 생성합니다."""
    return SuccessResponse(success=True, data=data)


def fail(
    *,
    code: ErrorCode | str,
    message: str,
    details: Any | None = None,
) -> ResponseEnvelope[None]:
    """프로토콜 경계에서 사용할 실패 response envelope를 생성합니다."""
    code_value = code.value if isinstance(code, ErrorCode) else code
    return ResponseEnvelope(
        success=False,
        data=None,
        error=ErrorInfo(code=code_value, message=message, details=details),
    )
