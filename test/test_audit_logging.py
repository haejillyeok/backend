import logging

from fastapi.testclient import TestClient

from app.be.main import create_app as create_be_app
from app.shared.core.audit import AuditEvent, log_audit_event


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
