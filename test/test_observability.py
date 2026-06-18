from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from starlette.responses import Response

import app.shared.core.observability as observability
from app.be.services.lobby import message_delivery as lobby_delivery
from app.be.services.match.connection_manager import MatchConnectionManager
from app.be.services.match import connection_manager as match_connection_manager_module
from app.shared.core.observability import (
    HttpServerMetricsMiddleware,
    HttpServerTracingMiddleware,
    ObservabilitySettings,
    WebSocketServerMetrics,
    add_observability,
    configure_observability_sdk,
    resolve_otlp_http_endpoint,
    start_root_span,
)


class RecordingMetric:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, dict | None]] = []

    def add(self, amount: int, attributes: dict | None = None) -> None:
        self.calls.append(("add", amount, attributes))

    def record(self, amount: float, attributes: dict | None = None) -> None:
        self.calls.append(("record", amount, attributes))


class RecordingMeter:
    def __init__(self) -> None:
        self.counters: dict[str, RecordingMetric] = {}
        self.histograms: dict[str, RecordingMetric] = {}
        self.up_down_counters: dict[str, RecordingMetric] = {}

    def create_counter(self, name: str, **kwargs):
        metric = RecordingMetric()
        self.counters[name] = metric
        return metric

    def create_histogram(self, name: str, **kwargs):
        metric = RecordingMetric()
        self.histograms[name] = metric
        return metric

    def create_up_down_counter(self, name: str, **kwargs):
        metric = RecordingMetric()
        self.up_down_counters[name] = metric
        return metric


def test_disabled_observability_does_not_install_fastapi_middleware() -> None:
    app = FastAPI()

    add_observability(
        app,
        "haejillyeok-test",
        settings=ObservabilitySettings(enabled=False),
    )

    assert app.user_middleware == []


def test_disabled_observability_sdk_configuration_is_noop() -> None:
    configure_observability_sdk(
        ObservabilitySettings(enabled=False),
        "haejillyeok-test",
    )


def test_otlp_endpoint_resolution_keeps_tenant_query_and_signal_path() -> None:
    assert (
        resolve_otlp_http_endpoint(
            "http://localhost:4318/custom/v1/metrics?tenant=local",
            signal_path="/v1/metrics",
        )
        == "http://localhost:4318/custom/v1/metrics?tenant=local"
    )
    assert (
        resolve_otlp_http_endpoint(
            "http://localhost:4318/custom",
            signal_path="/v1/traces",
        )
        == "http://localhost:4318/custom/v1/traces"
    )


def test_start_root_span_starts_with_empty_context(monkeypatch) -> None:
    contexts: list[object] = []

    class FakeContextApi:
        @staticmethod
        def Context():
            return {"root": True}

    class FakeTracer:
        def start_as_current_span(self, span_name, *, attributes=None, context=None):
            contexts.append(context)
            return FakeSpan()

    class FakeTrace:
        @staticmethod
        def get_tracer(name):
            return FakeTracer()

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

    monkeypatch.setattr(observability, "trace", FakeTrace)
    monkeypatch.setattr(observability, "otel_context", FakeContextApi)

    with start_root_span("WebSocket.lobby.message", attributes={"ws.message.type": "ping"}):
        pass

    assert contexts == [{"root": True}]


async def test_http_tracing_middleware_starts_each_request_as_root_trace(monkeypatch) -> None:
    contexts: list[object] = []
    span_names: list[str] = []
    span_attributes: list[tuple[str, object]] = []

    class FakeContextApi:
        @staticmethod
        def Context():
            return {"root": True}

    class FakeTracer:
        def start_as_current_span(self, span_name, *, attributes=None, context=None, **kwargs):
            contexts.append(context)
            span_names.append(span_name)
            return FakeSpan()

    class FakeTrace:
        @staticmethod
        def get_tracer(name):
            return FakeTracer()

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

        def set_attribute(self, key, value):
            span_attributes.append((key, value))

        def update_name(self, name):
            span_names.append(name)

    monkeypatch.setattr(observability, "trace", FakeTrace)
    monkeypatch.setattr(observability, "otel_context", FakeContextApi)

    middleware = HttpServerTracingMiddleware(FastAPI(), "haejillyeok-test")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 50000),
        }
    )

    async def return_ok(request: Request):
        return Response(status_code=200)

    response = await middleware.dispatch(request, return_ok)

    assert response.status_code == 200
    assert contexts == [{"root": True}]
    assert span_names[0] == "POST /api/v1/auth/login"
    assert ("http.response.status_code", 200) in span_attributes


def test_http_route_template_restores_nested_router_prefix() -> None:
    class FakeRoute:
        path_format = "/game/rooms/{room_public_id}/join"

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/game/rooms/019ed7fd-03e3-7e56-b529-6b4bd171f3c0/join",
            "path_params": {"room_public_id": "019ed7fd-03e3-7e56-b529-6b4bd171f3c0"},
            "route": FakeRoute(),
            "headers": [],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 50000),
        }
    )

    assert (
        observability._http_route_template(request, fallback_to_path=True)
        == "/api/v1/game/rooms/{room_public_id}/join"
    )


async def test_match_websocket_broadcast_records_broadcast_and_send_spans(monkeypatch) -> None:
    span_names: list[str] = []
    span_attributes: list[dict | None] = []

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

    def fake_start_span(name, attributes=None):
        span_names.append(name)
        span_attributes.append(attributes)
        return FakeSpan()

    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent_messages = []

        async def send_json(self, message) -> None:
            self.sent_messages.append(message)

    monkeypatch.setattr(
        match_connection_manager_module,
        "start_span",
        fake_start_span,
        raising=False,
    )

    manager = MatchConnectionManager()
    websocket = FakeWebSocket()
    session_public_id = "019ed7fd-03e3-7e56-b529-6b4bd171f3c0"
    manager._session_subscriptions[session_public_id] = {websocket}

    await manager.broadcast_session(
        session_public_id,
        {"type": "match.turn.resolved", "payload": {}},
    )

    assert span_names == ["WebSocket.match.broadcast", "WebSocket.match.send"]
    assert span_attributes[0]["ws.message.type"] == "match.turn.resolved"
    assert span_attributes[0]["ws.subscriber.count"] == 1
    assert span_attributes[1]["ws.message.type"] == "match.turn.resolved"


async def test_lobby_websocket_send_records_send_span(monkeypatch) -> None:
    span_names: list[str] = []
    span_attributes: list[dict | None] = []

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

    def fake_start_span(name, attributes=None):
        span_names.append(name)
        span_attributes.append(attributes)
        return FakeSpan()

    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent_messages = []

        async def send_json(self, message) -> None:
            self.sent_messages.append(message)

    monkeypatch.setattr(lobby_delivery, "start_span", fake_start_span, raising=False)

    await lobby_delivery.send_lobby_message(
        FakeWebSocket(),
        {"type": "lobby.pong", "payload": {}},
    )

    assert span_names == ["WebSocket.lobby.send"]
    assert span_attributes[0]["ws.message.type"] == "lobby.pong"
    assert span_attributes[0]["ws.message.direction"] == "outbound"


def test_websocket_endpoint_spans_are_root_trace_boundaries() -> None:
    websocket_modules = [
        "app/be/api/endpoints/lobby_ws/connection.py",
        "app/be/api/endpoints/lobby_ws/message_loop.py",
        "app/be/api/endpoints/lobby_ws/grace_leave.py",
        "app/be/api/endpoints/match_ws/connection.py",
        "app/be/api/endpoints/match_ws/connection_lifecycle.py",
        "app/be/api/endpoints/match_ws/loop_message_processing.py",
    ]

    for module_path in websocket_modules:
        source = Path(module_path).read_text(encoding="utf-8")
        assert "start_root_span" in source
        assert "import start_span" not in source


def test_websocket_message_loops_include_receive_and_handle_child_spans() -> None:
    expected_spans = {
        "app/be/api/endpoints/lobby_ws/message_loop.py": [
            "WebSocket.lobby.receive",
            "WebSocket.lobby.handle",
        ],
        "app/be/api/endpoints/match_ws/loop_message_processing.py": [
            "WebSocket.match.receive",
            "WebSocket.match.handle",
        ],
    }

    for module_path, span_names in expected_spans.items():
        source = Path(module_path).read_text(encoding="utf-8")
        for span_name in span_names:
            assert span_name in source


async def test_http_metrics_middleware_records_request_error_metrics() -> None:
    meter = RecordingMeter()
    middleware = HttpServerMetricsMiddleware(FastAPI(), "haejillyeok-test", meter=meter)
    request = Request({"type": "http", "method": "GET", "path": "/boom"})

    async def raise_error(request: Request):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await middleware.dispatch(request, raise_error)

    request_counter = meter.counters["http.server.requests"]
    error_counter = meter.counters["http.server.errors"]
    duration_histogram = meter.histograms["http.server.request.duration"]
    assert request_counter.calls[0][0] == "add"
    assert error_counter.calls[0][0] == "add"
    assert duration_histogram.calls[0][0] == "record"
    assert request_counter.calls[0][2]["http.route"] == "unmatched"
    assert request_counter.calls[0][2]["http.response.status_code"] == 500


async def test_http_metrics_middleware_records_5xx_response_metrics() -> None:
    meter = RecordingMeter()
    middleware = HttpServerMetricsMiddleware(FastAPI(), "haejillyeok-test", meter=meter)
    request = Request({"type": "http", "method": "POST", "path": "/error"})

    async def return_error(request: Request):
        return Response(status_code=503)

    response = await middleware.dispatch(request, return_error)

    assert response.status_code == 503
    assert meter.counters["http.server.errors"].calls[0][2]["http.response.status_code"] == 503


def test_websocket_metrics_record_connection_message_and_disconnect() -> None:
    meter = RecordingMeter()
    recorder = WebSocketServerMetrics("haejillyeok-test", meter=meter)

    recorder.record_connect(
        ws_route="/ws/lobby/rooms/{room_public_id}",
        ws_endpoint="lobby",
    )
    recorder.record_message(
        ws_route="/ws/lobby/rooms/{room_public_id}",
        ws_endpoint="lobby",
        message_type="ping",
        direction="inbound",
    )
    recorder.record_message_duration(
        ws_route="/ws/lobby/rooms/{room_public_id}",
        ws_endpoint="lobby",
        message_type="ping",
        duration_seconds=0.05,
    )
    recorder.record_error(
        ws_route="/ws/lobby/rooms/{room_public_id}",
        ws_endpoint="lobby",
        error_type="timeout",
    )
    recorder.record_disconnect(
        ws_route="/ws/lobby/rooms/{room_public_id}",
        ws_endpoint="lobby",
        close_code=1001,
    )
    recorder.record_duration(
        ws_route="/ws/lobby/rooms/{room_public_id}",
        ws_endpoint="lobby",
        duration_seconds=1.5,
        close_code=1001,
    )

    active_calls = meter.up_down_counters["websocket.connections.active"].calls
    assert active_calls[0] == (
        "add",
        1,
        {
            "service.name": "haejillyeok-test",
            "ws.route": "/ws/lobby/rooms/{room_public_id}",
            "ws.endpoint": "lobby",
        },
    )
    assert active_calls[1][1] == -1
    assert meter.counters["websocket.connections.total"].calls[0][1] == 1
    assert meter.counters["websocket.messages.total"].calls[0][2]["ws.message.type"] == "ping"
    assert meter.histograms["websocket.message.duration"].calls[0] == (
        "record",
        0.05,
        {
            "service.name": "haejillyeok-test",
            "ws.route": "/ws/lobby/rooms/{room_public_id}",
            "ws.endpoint": "lobby",
            "ws.message.type": "ping",
        },
    )
    assert meter.counters["websocket.errors.total"].calls[0][2]["ws.error.type"] == "timeout"
    assert meter.counters["websocket.disconnects.total"].calls[0][2]["ws.close_code"] == "1001"
    assert meter.histograms["websocket.connection.duration"].calls[0][1] == 1.5
