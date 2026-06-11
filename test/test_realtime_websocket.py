import pytest
from fastapi.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.be.main import create_app
from app.be.services.realtime import realtime_connection_manager


def test_realtime_websocket_returns_pong_and_cleans_up_connection():
    client = TestClient(create_app())

    with client.websocket_connect("/ws/realtime") as websocket:
        assert realtime_connection_manager.connection_count == 1

        websocket.send_json({"type": "ping", "payload": {"client_time": "2026-06-11T00:00:00Z"}})

        assert websocket.receive_json() == {
            "type": "realtime.pong",
            "payload": {"client_time": "2026-06-11T00:00:00Z"},
        }

    assert realtime_connection_manager.connection_count == 0


def test_realtime_websocket_rejects_invalid_json_envelope():
    client = TestClient(create_app())

    with client.websocket_connect("/ws/realtime") as websocket:
        websocket.send_text("not-json")

        assert websocket.receive_json() == {
            "type": "error",
            "payload": {
                "success": False,
                "data": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "요청 값이 올바르지 않습니다.",
                    "details": {"reason": "json_parse_error"},
                },
            },
        }
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 1008
    assert realtime_connection_manager.connection_count == 0


def test_realtime_websocket_rejects_unknown_message_type():
    client = TestClient(create_app())

    with client.websocket_connect("/ws/realtime") as websocket:
        websocket.send_json({"type": "unknown", "payload": {}})

        assert websocket.receive_json()["payload"]["error"]["details"] == {
            "reason": "unsupported_message_type",
            "type": "unknown",
        }
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 1008
    assert realtime_connection_manager.connection_count == 0


def test_ws_docs_renders_websocket_api_page():
    client = TestClient(create_app())

    response = client.get("/ws-docs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "content-disposition" not in response.headers
    assert "<h1>WebSocket API</h1>" in response.text
    assert "wss://&lt;host&gt;/ws/realtime" in response.text
    assert "&quot;type&quot;: &quot;ping&quot;" in response.text
    assert "&quot;type&quot;: &quot;realtime.pong&quot;" in response.text
