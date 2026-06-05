from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

import grpc

from app.shared.core.audit import AuditEvent, log_audit_event
from app.shared.core.exceptions import AppException


UnaryUnaryHandler = Callable[[Any, grpc.aio.ServicerContext], Awaitable[Any]]


class AuditServerInterceptor(grpc.aio.ServerInterceptor):
    """gRPC 요청 시작과 종료를 감사 로그로 남기는 interceptor입니다."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name

    async def intercept_service(self, continuation, handler_call_details):
        """RPC method handler를 감싸 protocol-neutral 감사 로그를 기록합니다."""
        handler = await continuation(handler_call_details)
        if handler is None or handler.unary_unary is None:
            return handler

        method = handler_call_details.method
        wrapped_unary_unary = self._wrap_unary_unary(handler.unary_unary, method)
        return grpc.unary_unary_rpc_method_handler(
            wrapped_unary_unary,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )

    def _wrap_unary_unary(
        self,
        handler: UnaryUnaryHandler,
        method: str,
    ) -> UnaryUnaryHandler:
        async def wrapper(request, context):
            peer = context.peer()
            started_at = perf_counter()
            log_audit_event(
                AuditEvent(
                    protocol="grpc",
                    phase="started",
                    service=self.service_name,
                    operation=method,
                    peer=peer,
                )
            )

            try:
                response = await handler(request, context)
            except AppException as exc:
                duration_ms = (perf_counter() - started_at) * 1000
                log_audit_event(
                    AuditEvent(
                        protocol="grpc",
                        phase="failed",
                        service=self.service_name,
                        operation=method,
                        status_code=exc.grpc_status_code.name,
                        duration_ms=duration_ms,
                        peer=peer,
                        error_code=exc.code,
                    )
                )
                await context.abort(exc.grpc_status_code, exc.message)
            except Exception as exc:
                duration_ms = (perf_counter() - started_at) * 1000
                log_audit_event(
                    AuditEvent(
                        protocol="grpc",
                        phase="failed",
                        service=self.service_name,
                        operation=method,
                        status_code=grpc.StatusCode.UNKNOWN.name,
                        duration_ms=duration_ms,
                        peer=peer,
                        error_code=exc.__class__.__name__,
                    )
                )
                raise

            duration_ms = (perf_counter() - started_at) * 1000
            log_audit_event(
                AuditEvent(
                    protocol="grpc",
                    phase="completed",
                    service=self.service_name,
                    operation=method,
                    status_code=grpc.StatusCode.OK.name,
                    duration_ms=duration_ms,
                    peer=peer,
                )
            )
            return response

        return wrapper
