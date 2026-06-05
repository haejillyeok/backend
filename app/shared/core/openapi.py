from typing import Any

from fastapi import FastAPI

from app.shared.core.error_codes import (
    ErrorCode,
    ErrorDefinition,
    get_error_definition,
    get_error_type_description,
)
from app.shared.core.responses import ErrorResponse


ERROR_RESPONSE_REF = "#/components/schemas/ErrorResponse"


def error_example(
    *,
    name: str,
    summary: str | None = None,
    code: ErrorCode | str,
    message: str | None = None,
    details: Any | None = None,
) -> dict[str, Any]:
    """같은 HTTP status 안에 표시할 개별 application error 예시를 만듭니다."""
    definition = get_error_definition(code)
    return {
        "name": name,
        "summary": summary or definition.summary,
        "value": {
            "success": False,
            "data": None,
            "error": {
                "code": definition.code.value,
                "message": message or definition.message,
                "details": details,
            },
        },
    }


def error_response(
    *,
    code: ErrorCode | str,
    message: str,
    description: str,
    details: Any | None = None,
) -> dict[str, Any]:
    """Swagger에 공통 error envelope 모델과 예시 응답을 함께 표시합니다."""
    definition = get_error_definition(code)
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "example": {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": definition.code.value,
                        "message": message or definition.message,
                        "details": details,
                    },
                },
            },
        },
    }


def error_responses(
    *,
    description: str,
    examples: list[dict[str, Any]],
) -> dict[str, Any]:
    """하나의 HTTP status에 여러 application error 예시를 표시합니다."""
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "examples": {
                    example["name"]: {
                        "summary": example["summary"],
                        "value": example["value"],
                    }
                    for example in examples
                },
            },
        },
    }


def error_responses_by_status(
    *,
    codes: list[ErrorCode | str],
) -> dict[int, dict[str, Any]]:
    """ErrorCode 목록을 HTTP status별 Swagger responses로 그룹핑합니다."""
    definitions_by_status: dict[int, list[ErrorDefinition]] = {}
    for code in codes:
        definition = get_error_definition(code)
        definitions_by_status.setdefault(definition.http_status_code, []).append(definition)

    return {
        status_code: error_responses(
            description=get_error_type_description(definitions[0].type),
            examples=[
                error_example(
                    name=definition.example_name,
                    code=definition.code,
                )
                for definition in definitions
            ],
        )
        for status_code, definitions in definitions_by_status.items()
    }


def install_openapi_schema(app: FastAPI) -> None:
    """FastAPI가 제거하는 error example의 null 필드를 OpenAPI 계약에 맞게 복원합니다."""
    base_openapi = app.openapi

    def custom_openapi() -> dict[str, Any]:
        schema = base_openapi()
        restore_error_response_null_examples(schema)
        return schema

    app.openapi = custom_openapi


def restore_error_response_null_examples(schema: dict[str, Any]) -> None:
    """ErrorResponse를 쓰는 response example에 envelope null 필드를 명시합니다."""
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            if not isinstance(operation, dict):
                continue
            for response in operation.get("responses", {}).values():
                content = response.get("content", {}).get("application/json", {})
                if content.get("schema", {}).get("$ref") != ERROR_RESPONSE_REF:
                    continue
                restore_error_example_nulls(content.get("example"))
                for example in content.get("examples", {}).values():
                    if isinstance(example, dict):
                        restore_error_example_nulls(example.get("value"))


def restore_error_example_nulls(example: Any) -> None:
    """ErrorResponse example에 생략되기 쉬운 null 필드를 되살립니다."""
    if not isinstance(example, dict):
        return
    example["data"] = None
    error = example.get("error")
    if isinstance(error, dict):
        error["details"] = error.get("details")
