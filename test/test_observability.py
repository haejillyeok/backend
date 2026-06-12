import pytest
from fastapi import FastAPI, Request
from starlette.responses import Response

from app.shared.core.observability import (
    HttpServerMetricsMiddleware,
    ObservabilitySettings,
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
        self.request_counter = RecordingMetric()
        self.error_counter = RecordingMetric()
        self.duration_histogram = RecordingMetric()
        self.counter_calls = 0

    def create_counter(self, name: str, **kwargs):
        self.counter_calls += 1
        if self.counter_calls == 1:
            return self.request_counter
        return self.error_counter

    def create_histogram(self, name: str, **kwargs):
        return self.duration_histogram


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


async def test_http_metrics_middleware_records_request_error_metrics() -> None:
    meter = RecordingMeter()
    middleware = HttpServerMetricsMiddleware(FastAPI(), "haejillyeok-test", meter=meter)
    request = Request({"type": "http", "method": "GET", "path": "/boom"})

    async def raise_error(request: Request):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await middleware.dispatch(request, raise_error)

    assert meter.request_counter.calls[0][0] == "add"
    assert meter.error_counter.calls[0][0] == "add"
    assert meter.duration_histogram.calls[0][0] == "record"
    assert meter.request_counter.calls[0][2]["http.route"] == "unmatched"
    assert meter.request_counter.calls[0][2]["http.response.status_code"] == 500


async def test_http_metrics_middleware_records_5xx_response_metrics() -> None:
    meter = RecordingMeter()
    middleware = HttpServerMetricsMiddleware(FastAPI(), "haejillyeok-test", meter=meter)
    request = Request({"type": "http", "method": "POST", "path": "/error"})

    async def return_error(request: Request):
        return Response(status_code=503)

    response = await middleware.dispatch(request, return_error)

    assert response.status_code == 503
    assert meter.error_counter.calls[0][2]["http.response.status_code"] == 503
