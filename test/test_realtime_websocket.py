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
    assert '<h1 id="websocket-api">WebSocket API</h1>' in response.text
    assert 'id="공통-메시지-규칙"' in response.text
    assert 'id="메시지-방향"' in response.text
    assert 'id="로비-websocket"' in response.text
    assert "wss://&lt;host&gt;/ws/realtime" in response.text
    assert "wss://&lt;host&gt;/ws/lobby/rooms/{room_public_id}" in response.text
    assert "&quot;type&quot;: &quot;ping&quot;" in response.text
    assert "&quot;type&quot;: &quot;realtime.pong&quot;" in response.text
    assert "요청(Request)" in response.text
    assert "응답(Response)" in response.text
    assert "이벤트(Event)" in response.text
    assert "match.turn.resolved" in response.text
    assert "SESSION_EXPIRED" in response.text
    assert "GAME_ROOM_NOT_FOUND" in response.text
    assert "GAME_ROOM_ENTRY_FORBIDDEN" in response.text
    assert "GAME_SESSION_ENTRY_FORBIDDEN" in response.text
    assert "VALIDATION_ERROR" in response.text
    assert "HTTP_ERROR" in response.text
    assert "match.word.accepted" not in response.text
    assert "match.word.rejected" not in response.text
    assert "match.turn.failed" not in response.text
    assert "match.turn.timeout" not in response.text


def test_ws_docs_renders_full_width_collapsible_sections_and_split_mermaid_user_flows():
    client = TestClient(create_app())

    response = client.get("/ws-docs")

    assert response.status_code == 200
    assert "width: calc(100% - 32px);" in response.text
    assert 'class="doc-toolbar"' in response.text
    assert 'class="doc-section"' in response.text
    assert "<summary" in response.text
    assert "모두 펼치기" in response.text
    assert "모두 접기" in response.text
    assert '<nav class="toc" aria-label="문서 목차">' in response.text
    assert '<a href="#로비-websocket">' in response.text
    assert '<a href="#사용자-흐름">' in response.text
    assert '<a href="#요청-request-ping">' not in response.text
    assert 'id="로비-연결"' in response.text
    assert 'id="객실-생성과-참여"' in response.text
    assert 'id="게임-시작과-매치-연결"' in response.text
    assert 'id="게임-진행과-판정-동기화"' in response.text
    assert response.text.count('<pre class="mermaid">') == 4
    assert response.text.count("sequenceDiagram") == 4
    assert "mermaid.initialize" in response.text
