import pytest
from fastapi import FastAPI, Request
from starlette.responses import Response

from app.shared.core.observability import (
    HttpServerMetricsMiddleware,
    ObservabilitySettings,
    WebSocketServerMetrics,
    _safe_fastapi_route_details,
    add_observability,
    configure_observability_sdk,
    resolve_otlp_http_endpoint,
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


def test_safe_fastapi_route_details_falls_back_when_instrumentation_route_breaks() -> None:
    def raise_included_router_error(scope):
        raise AttributeError("'_IncludedRouter' object has no attribute 'path'")

    route = _safe_fastapi_route_details(
        {"path": "/api/v1/auth/login"},
        raise_included_router_error,
    )

    assert route == "/api/v1/auth/login"


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
