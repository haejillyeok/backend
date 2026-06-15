import logging

from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect
import pytest

from app.be.main import create_app as create_be_app
from app.shared.core.audit import AuditEvent, log_audit_event, redact_audit_payload


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


def test_be_blocks_unknown_paths_without_audit_log(caplog):
    caplog.set_level(logging.INFO, logger="audit.request")
    client = TestClient(create_be_app())

    for path in (
        "/static/js/main.chunk.js.map",
        "/.env",
        "/api/v1/missing",
    ):
        caplog.clear()

        response = client.get(path)

        assert response.status_code == 404
        assert response.content == b""
        assert not any(
            record.name == "audit.request" and path in record.message for record in caplog.records
        )


def test_audit_payload_redacts_sensitive_nested_values() -> None:
    assert redact_audit_payload(
        {
            "account_id": "player_001",
            "password": "secret-password",
            "headers": {
                "X-Agent-API-Key": "agent-secret",
                "Content-Type": "application/json",
            },
            "payload": {
                "game_session_token": "resume-token",
                "used_words": ["사과", "과자"],
            },
        }
    ) == {
        "account_id": "player_001",
        "password": "***REDACTED***",
        "headers": {
            "X-Agent-API-Key": "***REDACTED***",
            "Content-Type": "application/json",
        },
        "payload": {
            "game_session_token": "***REDACTED***",
            "used_words": ["사과", "과자"],
        },
    }


def test_realtime_websocket_writes_audit_logs_for_connection_message_and_disconnect(caplog):
    caplog.set_level(logging.INFO, logger="audit.request")
    client = TestClient(create_be_app())

    with client.websocket_connect("/ws/realtime") as websocket:
        websocket.send_json(
            {
                "type": "ping",
                "payload": {
                    "client_time": "2026-06-15T00:00:00Z",
                    "session_token": "plain-token",
                },
            }
        )
        assert websocket.receive_json()["type"] == "realtime.pong"

    audit_messages = [
        record.message for record in caplog.records if record.name == "audit.request"
    ]
    assert any(
        "audit protocol=websocket phase=completed service=haejillyeok-be "
        "operation=CONNECT /ws/realtime status_code=101" in message
        for message in audit_messages
    )
    assert any(
        "operation=MESSAGE /ws/realtime status_code=200" in message
        and "message_type=ping" in message
        and "payload=" in message
        and "plain-token" not in message
        for message in audit_messages
    )
    assert any(
        "operation=DISCONNECT /ws/realtime status_code=1000" in message
        for message in audit_messages
    )


def test_realtime_websocket_writes_failed_audit_log_for_invalid_message(caplog):
    caplog.set_level(logging.INFO, logger="audit.request")
    client = TestClient(create_be_app())

    with client.websocket_connect("/ws/realtime") as websocket:
        websocket.send_text("not-json")
        assert websocket.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()

    assert any(
        record.name == "audit.request"
        and "audit protocol=websocket phase=failed service=haejillyeok-be "
        "operation=MESSAGE /ws/realtime status_code=1008" in record.message
        and "error_code=VALIDATION_ERROR" in record.message
        for record in caplog.records
    )
