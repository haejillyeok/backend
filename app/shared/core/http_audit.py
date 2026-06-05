from time import perf_counter

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.shared.core.audit import AuditEvent, log_audit_event


class AuditLogMiddleware(BaseHTTPMiddleware):
    """FastAPI 요청 시작과 종료를 감사 로그로 남기는 middleware입니다."""

    def __init__(self, app: FastAPI, service_name: str) -> None:
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """요청 payload 없이 method/path/status/duration 중심으로 감사 로그를 남깁니다."""
        operation = f"{request.method} {request.url.path}"
        peer = request.client.host if request.client else None
        started_at = perf_counter()
        log_audit_event(
            AuditEvent(
                protocol="http",
                phase="started",
                service=self.service_name,
                operation=operation,
                peer=peer,
            )
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (perf_counter() - started_at) * 1000
            log_audit_event(
                AuditEvent(
                    protocol="http",
                    phase="failed",
                    service=self.service_name,
                    operation=operation,
                    status_code="500",
                    duration_ms=duration_ms,
                    peer=peer,
                    error_code=exc.__class__.__name__,
                )
            )
            raise

        duration_ms = (perf_counter() - started_at) * 1000
        log_audit_event(
            AuditEvent(
                protocol="http",
                phase="completed",
                service=self.service_name,
                operation=operation,
                status_code=str(response.status_code),
                duration_ms=duration_ms,
                peer=peer,
            )
        )
        return response


def add_audit_log_middleware(app: FastAPI, service_name: str) -> None:
    """앱에 감사 로그 middleware를 등록합니다."""
    app.add_middleware(AuditLogMiddleware, service_name=service_name)
