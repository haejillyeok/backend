import logging
from time import perf_counter
from typing import Any, Callable, ParamSpec, TypeVar
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, Request
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

try:
    from opentelemetry import context as otel_context
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import SpanKind
except ImportError:
    otel_context = None
    metrics = None
    trace = None
    OTLPMetricExporter = None
    OTLPSpanExporter = None
    MeterProvider = None
    PeriodicExportingMetricReader = None
    DEPLOYMENT_ENVIRONMENT = "deployment.environment"
    SERVICE_NAME = "service.name"
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    SpanKind = None


logger = logging.getLogger(__name__)
_SDK_CONFIGURED = False
P = ParamSpec("P")
R = TypeVar("R")
HTTP_DURATION_BUCKET_SECONDS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    10.0,
)
WEBSOCKET_DURATION_BUCKET_SECONDS = (
    1.0,
    5.0,
    15.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
    1800.0,
    3600.0,
)
WEBSOCKET_MESSAGE_DURATION_BUCKET_SECONDS = HTTP_DURATION_BUCKET_SECONDS


class ObservabilitySettings(BaseSettings):
    """OpenTelemetry exporter와 HTTP metric 수집 방식을 제어하는 설정입니다."""

    enabled: bool = Field(default=True, validation_alias="OTEL_ENABLED")
    otlp_endpoint: str = Field(
        default="http://localhost:4318",
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    metric_export_interval_ms: int = Field(
        default=5000,
        validation_alias="OTEL_METRIC_EXPORT_INTERVAL",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


class HttpServerMetricsMiddleware(BaseHTTPMiddleware):
    """FastAPI HTTP 요청의 latency, throughput, error rate용 OTel metric을 기록합니다."""

    def __init__(self, app: FastAPI, service_name: str, meter: Any | None = None) -> None:
        super().__init__(app)
        self.service_name = service_name
        self.meter = meter or _get_meter(service_name)
        self.request_counter = self.meter.create_counter(
            "http.server.requests",
            unit="{request}",
            description="HTTP server request throughput.",
        )
        self.error_counter = self.meter.create_counter(
            "http.server.errors",
            unit="{error}",
            description="HTTP server 5xx error count.",
        )
        self.duration_histogram = self.meter.create_histogram(
            "http.server.request.duration",
            unit="s",
            description="HTTP server request duration.",
            explicit_bucket_boundaries_advisory=HTTP_DURATION_BUCKET_SECONDS,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """route template 단위로 요청 수, 오류 수, 처리 시간을 metric에 기록합니다."""
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_seconds = perf_counter() - started_at
            attributes = _http_metric_attributes(request, self.service_name, 500)
            self.request_counter.add(1, attributes=attributes)
            self.error_counter.add(1, attributes=attributes)
            self.duration_histogram.record(duration_seconds, attributes=attributes)
            raise

        duration_seconds = perf_counter() - started_at
        attributes = _http_metric_attributes(request, self.service_name, response.status_code)
        self.request_counter.add(1, attributes=attributes)
        if response.status_code >= 500:
            self.error_counter.add(1, attributes=attributes)
        self.duration_histogram.record(duration_seconds, attributes=attributes)
        return response


class HttpServerTracingMiddleware(BaseHTTPMiddleware):
    """HTTP 요청마다 독립 root trace를 생성하고 하위 service/repository span을 묶습니다."""

    def __init__(self, app: FastAPI, service_name: str) -> None:
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """하나의 HTTP 요청을 하나의 root span으로 감싸고 응답 상태를 기록합니다."""
        span_name = _http_span_name(request)
        attributes = _http_trace_attributes(request, self.service_name)
        span_kind = SpanKind.SERVER if SpanKind is not None else None
        with start_root_span(span_name, attributes=attributes, kind=span_kind) as span:
            try:
                response = await call_next(request)
            except Exception:
                _set_span_attribute(span, "http.response.status_code", 500)
                _set_span_attribute(
                    span,
                    "http.route",
                    _http_route_template(request, fallback_to_path=True),
                )
                _update_span_name(span, _http_span_name(request))
                raise
            _set_span_attribute(span, "http.response.status_code", response.status_code)
            _set_span_attribute(
                span,
                "http.route",
                _http_route_template(request, fallback_to_path=True),
            )
            _update_span_name(span, _http_span_name(request))
            return response


class WebSocketServerMetrics:
    """WebSocket 연결, 메시지, 종료를 OpenTelemetry metric으로 기록합니다."""

    def __init__(self, service_name: str, meter: Any | None = None) -> None:
        self.service_name = service_name
        self.meter = meter or _get_meter(service_name)
        self.active_connections = self.meter.create_up_down_counter(
            "websocket.connections.active",
            unit="{connection}",
            description="Active WebSocket connections.",
        )
        self.connection_counter = self.meter.create_counter(
            "websocket.connections.total",
            unit="{connection}",
            description="Accepted WebSocket connections.",
        )
        self.message_counter = self.meter.create_counter(
            "websocket.messages.total",
            unit="{message}",
            description="WebSocket messages by direction and type.",
        )
        self.message_duration_histogram = self.meter.create_histogram(
            "websocket.message.duration",
            unit="s",
            description="WebSocket inbound message processing duration.",
            explicit_bucket_boundaries_advisory=WEBSOCKET_MESSAGE_DURATION_BUCKET_SECONDS,
        )
        self.error_counter = self.meter.create_counter(
            "websocket.errors.total",
            unit="{error}",
            description="WebSocket protocol or application errors.",
        )
        self.disconnect_counter = self.meter.create_counter(
            "websocket.disconnects.total",
            unit="{disconnect}",
            description="WebSocket disconnects by close code.",
        )
        self.duration_histogram = self.meter.create_histogram(
            "websocket.connection.duration",
            unit="s",
            description="WebSocket connection duration.",
            explicit_bucket_boundaries_advisory=WEBSOCKET_DURATION_BUCKET_SECONDS,
        )

    def record_connect(self, *, ws_route: str, ws_endpoint: str) -> None:
        """연결 수락 시 active connection과 총 연결 수 metric을 증가시킵니다."""
        attributes = self._base_attributes(ws_route=ws_route, ws_endpoint=ws_endpoint)
        self.active_connections.add(1, attributes=attributes)
        self.connection_counter.add(1, attributes=attributes)

    def record_message(
        self,
        *,
        ws_route: str,
        ws_endpoint: str,
        message_type: str,
        direction: str,
    ) -> None:
        """WebSocket message type과 방향별 처리량 metric을 기록합니다."""
        attributes = self._base_attributes(ws_route=ws_route, ws_endpoint=ws_endpoint)
        attributes["ws.message.type"] = message_type
        attributes["ws.message.direction"] = direction
        self.message_counter.add(1, attributes=attributes)

    def record_message_duration(
        self,
        *,
        ws_route: str,
        ws_endpoint: str,
        message_type: str,
        duration_seconds: float,
    ) -> None:
        """유효한 inbound WebSocket message의 서버 처리 시간을 histogram에 기록합니다."""
        attributes = self._base_attributes(ws_route=ws_route, ws_endpoint=ws_endpoint)
        attributes["ws.message.type"] = message_type
        self.message_duration_histogram.record(duration_seconds, attributes=attributes)

    def record_error(self, *, ws_route: str, ws_endpoint: str, error_type: str) -> None:
        """WebSocket 오류 발생 metric을 오류 유형별로 기록합니다."""
        attributes = self._base_attributes(ws_route=ws_route, ws_endpoint=ws_endpoint)
        attributes["ws.error.type"] = error_type
        self.error_counter.add(1, attributes=attributes)

    def record_disconnect(self, *, ws_route: str, ws_endpoint: str, close_code: int) -> None:
        """연결 종료 시 active connection 감소와 close code별 종료 metric을 기록합니다."""
        attributes = self._base_attributes(ws_route=ws_route, ws_endpoint=ws_endpoint)
        self.active_connections.add(-1, attributes=attributes)
        attributes["ws.close_code"] = str(close_code)
        self.disconnect_counter.add(1, attributes=attributes)

    def record_duration(
        self,
        *,
        ws_route: str,
        ws_endpoint: str,
        duration_seconds: float,
        close_code: int,
    ) -> None:
        """WebSocket 연결 지속 시간을 close code와 함께 histogram에 기록합니다."""
        attributes = self._base_attributes(ws_route=ws_route, ws_endpoint=ws_endpoint)
        attributes["ws.close_code"] = str(close_code)
        self.duration_histogram.record(duration_seconds, attributes=attributes)

    def _base_attributes(self, *, ws_route: str, ws_endpoint: str) -> dict[str, str]:
        return {
            "service.name": self.service_name,
            "ws.route": ws_route,
            "ws.endpoint": ws_endpoint,
        }


class _NoopWebSocketServerMetrics:
    def record_connect(self, *, ws_route: str, ws_endpoint: str) -> None:
        return None

    def record_message(
        self,
        *,
        ws_route: str,
        ws_endpoint: str,
        message_type: str,
        direction: str,
    ) -> None:
        return None

    def record_error(self, *, ws_route: str, ws_endpoint: str, error_type: str) -> None:
        return None

    def record_message_duration(
        self,
        *,
        ws_route: str,
        ws_endpoint: str,
        message_type: str,
        duration_seconds: float,
    ) -> None:
        return None

    def record_disconnect(self, *, ws_route: str, ws_endpoint: str, close_code: int) -> None:
        return None

    def record_duration(
        self,
        *,
        ws_route: str,
        ws_endpoint: str,
        duration_seconds: float,
        close_code: int,
    ) -> None:
        return None


NOOP_WEBSOCKET_METRICS = _NoopWebSocketServerMetrics()


def get_websocket_metrics(app: FastAPI):
    """FastAPI app.state에 등록된 WebSocket metric recorder를 반환합니다."""
    return getattr(app.state, "websocket_metrics", NOOP_WEBSOCKET_METRICS)


def add_observability(
    app: FastAPI,
    service_name: str,
    environment: str | None = None,
    settings: ObservabilitySettings | None = None,
) -> None:
    """FastAPI 앱에 OpenTelemetry trace instrumentation과 HTTP metric middleware를 등록합니다."""
    observability_settings = settings or ObservabilitySettings()
    if not observability_settings.enabled:
        return

    configure_observability_sdk(observability_settings, service_name, environment)
    app.state.websocket_metrics = WebSocketServerMetrics(service_name)
    app.add_middleware(HttpServerMetricsMiddleware, service_name=service_name)
    app.add_middleware(HttpServerTracingMiddleware, service_name=service_name)


def traced_method(
    span_name: str | None = None,
    *,
    layer: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """service/repository 메서드 실행 시간을 OpenTelemetry child span으로 기록합니다."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        resolved_span_name = span_name or _default_span_name(func)

        if _is_async_callable(func):

            async def async_wrapper(*args: P.args, **kwargs: P.kwargs):
                attributes = _method_span_attributes(func, args, layer)
                with start_span(resolved_span_name, attributes=attributes):
                    return await func(*args, **kwargs)

            return async_wrapper

        def sync_wrapper(*args: P.args, **kwargs: P.kwargs):
            attributes = _method_span_attributes(func, args, layer)
            with start_span(resolved_span_name, attributes=attributes):
                return func(*args, **kwargs)

        return sync_wrapper

    return decorator


def start_span(span_name: str, attributes: dict[str, Any] | None = None):
    """현재 요청 trace 아래에 수동 span을 생성합니다."""
    if trace is None:
        return _NoopSpan()
    return trace.get_tracer(__name__).start_as_current_span(span_name, attributes=attributes)


def start_root_span(
    span_name: str,
    attributes: dict[str, Any] | None = None,
    **kwargs: Any,
):
    """현재 active trace를 이어받지 않고 독립적인 root span을 생성합니다."""
    if trace is None or otel_context is None:
        return _NoopSpan()
    return trace.get_tracer(__name__).start_as_current_span(
        span_name,
        attributes=attributes,
        context=otel_context.Context(),
        **{key: value for key, value in kwargs.items() if value is not None},
    )


def configure_observability_sdk(
    settings: ObservabilitySettings,
    service_name: str,
    environment: str | None = None,
) -> None:
    """OTLP exporter를 사용하는 OpenTelemetry metric/trace SDK를 한 번만 초기화합니다."""
    global _SDK_CONFIGURED
    if _SDK_CONFIGURED:
        return
    if not settings.enabled:
        return
    if not _otel_sdk_available():
        logger.warning("OpenTelemetry SDK/exporter packages are not installed.")
        return

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            DEPLOYMENT_ENVIRONMENT: environment or "local",
        }
    )

    metric_exporter = OTLPMetricExporter(
        endpoint=resolve_otlp_http_endpoint(settings.otlp_endpoint, signal_path="/v1/metrics")
    )
    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=settings.metric_export_interval_ms,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    trace_exporter = OTLPSpanExporter(
        endpoint=resolve_otlp_http_endpoint(settings.otlp_endpoint, signal_path="/v1/traces")
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(tracer_provider)

    _SDK_CONFIGURED = True


def resolve_otlp_http_endpoint(base_endpoint: str, *, signal_path: str) -> str:
    """OTLP HTTP base endpoint를 signal별 ingest endpoint로 변환합니다.

    주요 입력은 `OTEL_EXPORTER_OTLP_ENDPOINT` 값과 `/v1/metrics` 같은 signal path입니다. 반환값은
    exporter에 넘길 전체 endpoint이며, 부작용은 없습니다.
    """
    parsed = urlsplit(base_endpoint)
    current_path = parsed.path.rstrip("/")
    known_signal_paths = {"/v1/metrics", "/v1/traces", "/v1/logs"}

    if not current_path:
        resolved_path = signal_path
    elif current_path in known_signal_paths:
        resolved_path = signal_path
    elif current_path.endswith(signal_path):
        resolved_path = current_path
    else:
        resolved_path = f"{current_path}{signal_path}"

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            resolved_path,
            parsed.query,
            parsed.fragment,
        )
    )


def _get_meter(service_name: str):
    if metrics is None:
        return _NoopMeter()
    return metrics.get_meter(service_name)


def _http_metric_attributes(
    request: Request,
    service_name: str,
    status_code: int,
) -> dict[str, str | int]:
    return {
        "service.name": service_name,
        "http.request.method": request.method,
        "http.route": _http_route_template(request),
        "http.response.status_code": status_code,
    }


def _http_trace_attributes(request: Request, service_name: str) -> dict[str, str | int]:
    attributes: dict[str, str | int] = {
        "service.name": service_name,
        "http.request.method": request.method,
        "http.route": _http_route_template(request, fallback_to_path=True),
        "url.path": request.url.path,
        "server.address": request.url.hostname or "",
    }
    if request.url.port is not None:
        attributes["server.port"] = request.url.port
    if request.client is not None:
        attributes["client.address"] = request.client.host
        attributes["client.port"] = request.client.port
    return attributes


def _http_span_name(request: Request) -> str:
    return f"{request.method} {_http_route_template(request, fallback_to_path=True)}"


def _http_route_template(request: Request, *, fallback_to_path: bool = False) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path_format", None) or getattr(route, "path", None)
    if route_path:
        return _with_request_path_prefix(
            str(route_path),
            request.scope.get("path") or "",
            request.scope.get("path_params") or {},
        )
    if fallback_to_path:
        return request.scope.get("path") or "unmatched"
    return "unmatched"


def _with_request_path_prefix(
    route_template: str,
    request_path: str,
    path_params: dict[str, Any],
) -> str:
    """중첩 router에서 빠진 prefix를 실제 path에서 복원하되 route parameter template은 유지합니다."""
    if not request_path:
        return route_template

    concrete_route_path = route_template
    for key, value in path_params.items():
        concrete_route_path = concrete_route_path.replace(f"{{{key}}}", str(value))

    if concrete_route_path and request_path.endswith(concrete_route_path):
        prefix = request_path[: -len(concrete_route_path)]
        return f"{prefix}{route_template}"

    return route_template


def _set_span_attribute(span: Any, key: str, value: Any) -> None:
    setter = getattr(span, "set_attribute", None)
    if setter is not None:
        setter(key, value)


def _update_span_name(span: Any, name: str) -> None:
    update_name = getattr(span, "update_name", None)
    if update_name is not None:
        update_name(name)


def _otel_sdk_available() -> bool:
    return all(
        dependency is not None
        for dependency in (
            metrics,
            trace,
            OTLPMetricExporter,
            OTLPSpanExporter,
            MeterProvider,
            PeriodicExportingMetricReader,
            Resource,
            TracerProvider,
            BatchSpanProcessor,
        )
    )


def _is_async_callable(func: Callable[..., Any]) -> bool:
    import inspect

    return inspect.iscoroutinefunction(func)


def _default_span_name(func: Callable[..., Any]) -> str:
    return f"{func.__module__}.{func.__qualname__}"


def _method_span_attributes(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    layer: str | None,
) -> dict[str, Any]:
    owner = args[0].__class__.__name__ if args else None
    attributes: dict[str, Any] = {
        "code.namespace": func.__module__,
        "code.function": func.__qualname__,
    }
    if owner:
        attributes["app.object"] = owner
    if layer:
        attributes["app.layer"] = layer
    return attributes


class _NoopMetric:
    def add(self, amount: int, attributes: dict[str, Any] | None = None) -> None:
        return None

    def record(self, amount: float, attributes: dict[str, Any] | None = None) -> None:
        return None


class _NoopMeter:
    def create_counter(self, name: str, **kwargs):
        return _NoopMetric()

    def create_histogram(self, name: str, **kwargs):
        return _NoopMetric()

    def create_up_down_counter(self, name: str, **kwargs):
        return _NoopMetric()


class _NoopSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False
