"""Shared application core utilities."""

from app.shared.core.audit import AuditEvent, format_audit_event, log_audit_event
from app.shared.core.error_codes import (
    ERROR_DEFINITIONS,
    ErrorCode,
    ErrorDefinition,
    ErrorType,
    get_error_definition,
)
from app.shared.core.exceptions import AppException, InvalidCredentialsError
from app.shared.core.http_audit import AuditLogMiddleware, add_audit_log_middleware
from app.shared.core.openapi import (
    error_example,
    error_response,
    error_responses,
    error_responses_by_status,
    install_openapi_schema,
)
from app.shared.core.responses import (
    ErrorInfo,
    ErrorResponse,
    ResponseEnvelope,
    SuccessResponse,
    fail,
    ok,
)

__all__ = [
    "AppException",
    "AuditEvent",
    "AuditLogMiddleware",
    "ERROR_DEFINITIONS",
    "ErrorCode",
    "ErrorDefinition",
    "ErrorInfo",
    "ErrorResponse",
    "ErrorType",
    "InvalidCredentialsError",
    "ResponseEnvelope",
    "SuccessResponse",
    "add_audit_log_middleware",
    "error_example",
    "error_response",
    "error_responses",
    "error_responses_by_status",
    "fail",
    "format_audit_event",
    "get_error_definition",
    "install_openapi_schema",
    "log_audit_event",
    "ok",
]
