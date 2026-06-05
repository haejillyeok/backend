import asyncio
import logging

from fastapi.testclient import TestClient

from app.agent.grpc import server as agent_grpc_server
from app.agent.grpc.server import create_grpc_server as create_agent_grpc_server
from app.be.main import create_app as create_be_app
from app.shared.core.audit import AuditEvent, log_audit_event
from app.shared.grpc.audit import AuditServerInterceptor


def test_audit_event_log_uses_stable_key_value_format(caplog):
    caplog.set_level(logging.INFO, logger="audit.request")

    log_audit_event(
        AuditEvent(
            protocol="http",
            phase="completed",
            service="haejillyeok-be",
            operation="GET /api/v1/health",
            status_code="200",
            duration_ms=12.34,
            peer="testclient",
        )
    )

    assert len(caplog.records) == 1
    assert caplog.records[0].message == (
        "audit protocol=http phase=completed service=haejillyeok-be "
        "operation=GET /api/v1/health status_code=200 duration_ms=12.34 "
        "peer=testclient"
    )


def test_be_http_api_writes_audit_log_for_request_completion(caplog):
    caplog.set_level(logging.INFO, logger="audit.request")
    client = TestClient(create_be_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert any(
        "audit protocol=http phase=completed service=haejillyeok-be "
        "operation=GET /api/v1/health status_code=200" in record.message
        for record in caplog.records
    )


def test_be_http_api_writes_audit_log_for_request_error(caplog):
    caplog.set_level(logging.INFO, logger="audit.request")
    client = TestClient(create_be_app())

    response = client.get("/api/v1/missing")

    assert response.status_code == 404
    assert any(
        "audit protocol=http phase=completed service=haejillyeok-be "
        "operation=GET /api/v1/missing status_code=404" in record.message
        for record in caplog.records
    )


def test_grpc_servers_register_audit_interceptor(monkeypatch):
    captured_interceptors = None

    class FakeGrpcServer:
        def add_generic_rpc_handlers(self, handlers):
            self.generic_handlers = handlers

        def add_registered_method_handlers(self, service_name, handlers):
            self.registered_service_name = service_name
            self.registered_handlers = handlers

    def capture_server_factory(*args, **kwargs):
        nonlocal captured_interceptors
        captured_interceptors = kwargs.get("interceptors")
        return FakeGrpcServer()

    monkeypatch.setattr(
        agent_grpc_server.grpc.aio,
        "server",
        capture_server_factory,
    )

    server = create_agent_grpc_server()

    assert isinstance(server, FakeGrpcServer)
    assert any(
        isinstance(interceptor, AuditServerInterceptor)
        for interceptor in captured_interceptors
    )


def test_grpc_audit_interceptor_logs_unary_completion(caplog):
    caplog.set_level(logging.INFO, logger="audit.request")
    interceptor = AuditServerInterceptor(service_name="haejillyeok-agent")

    class FakeContext:
        def peer(self) -> str:
            return "ipv4:127.0.0.1:50051"

    async def handler(request, context):
        return {"status": "ok"}

    wrapped_handler = interceptor._wrap_unary_unary(
        handler,
        "/haejillyeok.agent.internal.v1.InternalHealth/Ping",
    )

    result = asyncio.run(wrapped_handler(object(), FakeContext()))

    assert result == {"status": "ok"}
    assert any(
        "audit protocol=grpc phase=started service=haejillyeok-agent "
        "operation=/haejillyeok.agent.internal.v1.InternalHealth/Ping" in record.message
        for record in caplog.records
    )
    assert any(
        "audit protocol=grpc phase=completed service=haejillyeok-agent "
        "operation=/haejillyeok.agent.internal.v1.InternalHealth/Ping status_code=OK"
        in record.message
        for record in caplog.records
    )
