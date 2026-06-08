import logging
from time import perf_counter
from typing import Any, Callable, ParamSpec, TypeVar

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
    app.add_middleware(HttpServerMetricsMiddleware, service_name=service_name)

    if FastAPIInstrumentor is None:
        logger.warning("OpenTelemetry FastAPI instrumentation package is not installed.")
        return
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

    metric_exporter = OTLPMetricExporter(endpoint=settings.otlp_endpoint)
    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=settings.metric_export_interval_ms,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    trace_exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(tracer_provider)

    _SDK_CONFIGURED = True


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
