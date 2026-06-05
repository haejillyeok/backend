from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict


ResponseDataT = TypeVar("ResponseDataT")


class SharedModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorInfo(SharedModel):
    code: str
    message: str
    details: Any | None = None


class ResponseEnvelope(SharedModel, Generic[ResponseDataT]):
    success: bool
    data: ResponseDataT | None = None
    error: ErrorInfo | None = None


def ok(data: ResponseDataT) -> ResponseEnvelope[ResponseDataT]:
    """프로토콜 경계에서 사용할 성공 response envelope를 생성합니다."""
    return ResponseEnvelope(success=True, data=data, error=None)


def fail(
    *,
    code: str,
    message: str,
    details: Any | None = None,
) -> ResponseEnvelope[None]:
    """프로토콜 경계에서 사용할 실패 response envelope를 생성합니다."""
    return ResponseEnvelope(
        success=False,
        data=None,
        error=ErrorInfo(code=code, message=message, details=details),
    )
