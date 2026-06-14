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
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except ImportError:
    metrics = None
    trace = None
    OTLPMetricExporter = None
    OTLPSpanExporter = None
    FastAPIInstrumentor = None
    MeterProvider = None
    PeriodicExportingMetricReader = None
    DEPLOYMENT_ENVIRONMENT = "deployment.environment"
    SERVICE_NAME = "service.name"
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None


logger = logging.getLogger(__name__)
_SDK_CONFIGURED = False
_FASTAPI_ROUTE_DETAILS_FALLBACK_WARNED = False
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

    if FastAPIInstrumentor is None:
        logger.warning("OpenTelemetry FastAPI instrumentation package is not installed.")
        return
    _install_fastapi_route_details_fallback()
    FastAPIInstrumentor().instrument_app(app)


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


def _install_fastapi_route_details_fallback() -> None:
    """OTel FastAPI route 조회 버그가 실제 요청을 500으로 만들지 않게 보호합니다."""
    try:
        import opentelemetry.instrumentation.fastapi as fastapi_instrumentation
    except ImportError:
        return

    original_get_route_details = getattr(fastapi_instrumentation, "_get_route_details", None)
    if original_get_route_details is None:
        return
    if getattr(original_get_route_details, "_haejillyeok_safe_fallback", False):
        return

    def safe_get_route_details(scope: dict[str, Any]):
        return _safe_fastapi_route_details(scope, original_get_route_details)

    safe_get_route_details._haejillyeok_safe_fallback = True
    fastapi_instrumentation._get_route_details = safe_get_route_details


def _safe_fastapi_route_details(
    scope: dict[str, Any],
    get_route_details: Callable[[dict[str, Any]], str | None],
) -> str | None:
    """OTel route matcher가 router 중간 객체에서 실패하면 원 요청 path를 span route로 사용합니다."""
    global _FASTAPI_ROUTE_DETAILS_FALLBACK_WARNED
    try:
        return get_route_details(scope)
    except AttributeError as exc:
        if not _FASTAPI_ROUTE_DETAILS_FALLBACK_WARNED:
            logger.warning(
                "OpenTelemetry FastAPI route lookup failed; falling back to request path: %s",
                exc,
            )
            _FASTAPI_ROUTE_DETAILS_FALLBACK_WARNED = True
        return scope.get("path")


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


def _http_route_template(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path:
        return str(route_path)
    return "unmatched"


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
