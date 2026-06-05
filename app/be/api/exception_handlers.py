from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.core.exceptions import AppException
from app.shared.core.responses import fail


def register_exception_handlers(app: FastAPI) -> None:
    """BE REST API에서 발생하는 예외를 공통 error response로 변환합니다."""
    app.add_exception_handler(AppException, handle_app_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_exception)


async def handle_app_exception(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    """공통 애플리케이션 예외를 HTTP error envelope로 변환합니다."""
    return JSONResponse(
        status_code=exc.http_status_code,
        content=fail(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        ).model_dump(mode="json"),
    )


async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """FastAPI 요청 validation error를 필드 단위 details로 변환합니다."""
    return JSONResponse(
        status_code=422,
        content=fail(
            code="VALIDATION_ERROR",
            message="요청 값이 올바르지 않습니다.",
            details=[format_validation_error(error) for error in exc.errors()],
        ).model_dump(mode="json"),
    )


async def handle_http_exception(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """FastAPI HTTPException을 API 공통 error envelope로 변환합니다."""
    return JSONResponse(
        status_code=exc.status_code,
        content=fail(
            code="HTTP_ERROR",
            message=str(exc.detail),
        ).model_dump(mode="json"),
        headers=exc.headers,
    )


def format_validation_error(error: dict[str, Any]) -> dict[str, str]:
    """Pydantic validation error를 클라이언트가 읽기 쉬운 field/message/type으로 줄입니다."""
    location = ".".join(str(part) for part in error.get("loc", ()))
    return {
        "field": location,
        "message": str(error.get("msg", "")),
        "type": str(error.get("type", "")),
    }
