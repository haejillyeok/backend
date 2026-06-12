---
title: Observability Stack
type: guide
updated: 2026-06-10
audience: ai
---

# Observability Stack

이 레포의 로컬 관측은 OpenTelemetry, Prometheus, Tempo, Loki, Promtail, Grafana를 조합한다.

## Data Flow

```text
FastAPI app -> OTLP HTTP :4318 -> OpenTelemetry Collector -> Prometheus / Tempo -> Grafana
FastAPI app -> logs/*.log* -> Promtail -> Loki -> Grafana
```

- `app/shared/core/observability.py`는 FastAPI 앱에 OpenTelemetry trace instrumentation과
  HTTP metric middleware를 등록한다.
- `be`와 `agent` 앱은 `create_app()`에서 `add_observability()`를 호출한다.
- 앱 코드는 기본적으로 APM exporter를 연결하고, 별도 설정이 없으면 `http://localhost:4318`로
  OTLP HTTP를 보낸다. Docker 배포에서는 backend 컨테이너를 collector와 같은 user-defined
  network에 붙이고 `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`을 사용한다.
  특정 상황에서만 서버 `.env`의 값을 비활성화해 전송을 끈다.
- `OTEL_EXPORTER_OTLP_ENDPOINT`는 base endpoint로 관리하고, 앱 코드는 metric exporter에는
  `/v1/metrics`, trace exporter에는 `/v1/traces`를 붙여 Collector ingest endpoint로 보낸다.
- Docker Compose의 `otel-collector`는 OTLP HTTP `4318`을 열고,
  Prometheus scrape endpoint `9464`로 metric을 노출하며 trace는 Tempo로 전달한다.
- Prometheus는 `otel-collector:9464`를 scrape한다.
- Tempo는 trace span을 저장하고 Grafana Explore의 `Tempo` datasource로 조회된다.
- 앱 logger와 Uvicorn access/error logger는 stdout과 `logs/<app_name>.log`에 같은 포맷으로
  로그를 기록한다.
- 파일 로그는 매일 회전하고 기본 14일 동안 보관한다.
- 앱 시작 시와 파일 로그 emit 중 주기적으로 `LOG_DIR`의 `*.log*` 파일을 검사해
  `LOG_RETENTION_DAYS`보다 오래된 파일을 지우고, 전체 용량이 `LOG_MAX_TOTAL_BYTES`를 넘으면
  오래된 파일부터 삭제한다.
- Promtail은 `logs/*.log*` 파일을 tailing하고 `app_name`, `level`, `logger` label을 추출해
  Loki로 전송한다.
- Loki도 local stack에서 14일(`336h`) 보존 기간을 둔다.
- Grafana는 provisioned Prometheus/Tempo/Loki datasource와
  `docker/grafana/dashboards/fastapi-apm.json`, `fastapi-traces.json`, `fastapi-logs.json`
  dashboard를 사용한다.

## Metrics

FastAPI HTTP metric은 OpenTelemetry Meter API로 기록한다.

- `http.server.requests`: throughput counter
- `http.server.errors`: 5xx error counter
- `http.server.request.duration`: latency histogram, unit `s`
- HTTP latency histogram은 5ms부터 10s까지의 explicit bucket boundary를 사용한다.
- `websocket.connections.active`: 현재 열린 WebSocket connection up-down counter
- `websocket.connections.total`: 수락된 WebSocket connection counter
- `websocket.messages.total`: message type과 방향별 WebSocket message counter
- `websocket.errors.total`: WebSocket protocol/application error counter
- `websocket.disconnects.total`: close code별 WebSocket disconnect counter
- `websocket.connection.duration`: WebSocket connection duration histogram, unit `s`

Prometheus exporter는 OpenTelemetry metric과 attribute 이름을 Prometheus label/name으로 변환한다.
Grafana dashboard는 다음 Prometheus 이름을 기준으로 query한다.

- `http_server_requests_total`
- `http_server_errors_total`
- `http_server_request_duration_seconds_bucket`

## Label Rules

- route label은 실제 URL path가 아니라 FastAPI route template을 사용한다.
  - 예: `/items/abc`가 아니라 `/items/{item_id}`
- 404처럼 route가 매칭되지 않는 요청은 `http_route="unmatched"`로 집계한다.
- 기본 label은 `service_name`, `http_request_method`, `http_route`,
  `http_response_status_code`로 Prometheus에 노출되는 것을 전제로 한다.
- WebSocket label은 `service_name`, `ws_route`, `ws_endpoint`, `ws_message_type`,
  `ws_message_direction`, `ws_close_code`, `ws_error_type`처럼 낮은 cardinality 값만 사용한다.
- path parameter, request body, cookie, authorization header, session token, user id, room id 원문은
  metric label에 넣지 않는다.

## Object-Level Tracing

객체별 실행 시간은 metric label cardinality를 늘리지 않고 trace child span으로 남긴다.

- `app/shared/core/observability.py`의 `@traced_method(span_name, layer=...)`를 service,
  repository, external client wrapper 같은 의미 있는 경계에 붙인다.
- span attribute는 `app.object`, `app.layer`, `code.namespace`, `code.function`을 포함한다.
- service/repository/client 계층 span은 `app.layer` attribute로 구분해 trace dashboard에서 도메인에
  고정되지 않고 layer별로 조회한다.
- WebSocket endpoint는 `WebSocket.<endpoint>.connect`, `WebSocket.<endpoint>.message`,
  `WebSocket.<endpoint>.disconnect`, `WebSocket.<endpoint>.grace_leave` 같은 수동 span을 남긴다.
- password, token, request body, cookie, authorization header 값은 span attribute에 넣지 않는다.

## Local Commands

- 전체 관측 인프라 시작: `mise run infra-up`
- 전체 인프라 중지: `mise run infra-down`
- 인프라 로그 확인: `mise run infra-logs`

`mise` enter hook도 `mise run infra-up`을 실행하므로 프로젝트 디렉터리에 진입하면
PostgreSQL, OpenTelemetry Collector, Prometheus, Tempo, Grafana가 함께 시작된다.
Docker Compose의 host port는 인프라 실행 환경에서 바꿀 수 있다. 이 값들은 서버 `.env`
관리 대상이 아니다.

## Dashboard

Grafana metric dashboard는 `Haejillyeok FastAPI APM` 제목으로 provision 된다.

- Throughput: `rate(http_server_requests_total[...])`
- Error Rate: `http_server_errors_total / http_server_requests_total`, error series가 없으면 0으로 표시
- p95 latency: `histogram_quantile(0.95, rate(http_server_request_duration_seconds_bucket[...]))`
- p99 latency: `histogram_quantile(0.99, rate(http_server_request_duration_seconds_bucket[...]))`
- Throughput by Status: status code별 request rate

Grafana WebSocket metric dashboard는 `Haejillyeok WebSocket APM` 제목으로 provision 된다.

- Active Connections: route/endpoint별 현재 WebSocket 연결 수
- Connection Rate: 연결 수락 rate
- Message Rate: endpoint, message type, 방향별 message rate
- Error Rate: endpoint, error type별 error rate
- Disconnect Rate by Close Code: close code별 disconnect rate
- Connection Duration: WebSocket 연결 지속 시간 p95/p99

Grafana trace dashboard는 `Haejillyeok FastAPI Traces` 제목으로 provision 된다.

- Recent Request Traces: 요청 span 검색
- Service Layer Spans: `app.layer="service"` span 검색
- Repository Layer Spans: `app.layer="repository"` span 검색
- Selected Object Span Search: 선택한 service/repository span 검색

Trace 상세 waterfall은 dashboard table에서 trace를 열거나 Grafana Explore의 Tempo datasource에서 확인한다.

Grafana log dashboard는 `Haejillyeok FastAPI Logs` 제목으로 provision 된다.

- Log Volume by Level: level별 로그 건수. ERROR/CRITICAL은 빨간색 계열, WARNING/WARN은 노란색,
  INFO는 녹색, 그 외 level은 회색으로 표시한다.
- Error Logs: ERROR/CRITICAL 로그 건수
- Top Loggers: app, level, logger별 상위 로그 발생원
- Recent Logs: app, level, logger, 검색어 기준 로그 tail. 기본 검색어는 빈 값으로 두고 literal
  contains filter를 사용해 전체 라인 highlight를 피한다.
- Error Log Lines: ERROR/CRITICAL 로그 tail
- Audit Request Logs: `audit.request` logger 로그 tail

## Logs

파일 로그 설정은 `app/shared/core/logging_config.py`가 담당한다. Root logger뿐 아니라
`uvicorn`, `uvicorn.access` logger에도 같은 file handler를 붙여 Uvicorn access/error 로그가
파일에 남도록 한다. 로그 디렉터리 권한이나 경로 문제로 file handler를 만들 수 없으면 앱은
stdout logging만 유지하고 `File logging setup failed path=... Continuing with stdout logging only.`
ERROR 로그를 남긴다.
등록되지 않은 HTTP path를 route guard가 차단한 경우에는 해당 path의 Uvicorn access log도 필터링해
scanner 요청이 파일 로그를 채우지 않게 한다.

- `LOG_FILE_ENABLED`: 파일 로그 활성화 여부, 기본값 `true`
- `LOG_DIR`: 파일 로그 디렉터리, 기본값 `logs`
- `LOG_RETENTION_DAYS`: 날짜 기준 보존 기간, 기본값 `14`
- `LOG_MAX_TOTAL_BYTES`: `LOG_DIR` 안의 `*.log*` 전체 허용 용량, 기본값 `1073741824`
- `LOG_CLEANUP_INTERVAL_SECONDS`: 파일 로그 emit 중 정리 검사 간격, 기본값 `60`

로그 포맷은 Promtail regex와 연결되어 있으므로 바꿀 때는 `docker/promtail/promtail.yml`도 함께
갱신한다.

```text
%(asctime)s %(levelname)s [%(app_name)s] [%(name)s] %(message)s
```

Grafana Explore의 Loki datasource에서 `{job="haejillyeok-backend"}`,
`{app_name="haejillyeok-be"}`, `{level="ERROR"}` 같은 LogQL label selector로 조회한다.
Dashboard에서는 `job=haejillyeok-backend`를 기본값으로 두고 `app_name`, `level`, `logger`, `search`
변수로 같은 로그를 필터링한다. Grafana 기본 logs panel은 level별 전체 row 배경색을 provisioned
dashboard JSON에서 안정적으로 제어하지 못하므로, ERROR/CRITICAL 로그는 별도 log panel에서 분리해
확인한다.
