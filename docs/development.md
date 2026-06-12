# Development

## Setup

```bash
mise run install
```

## Database

백엔드 서버 실행 전 프로젝트 루트의 `.env`에 DB 접속 정보를 설정해야 합니다.
로컬 설정 예시를 사용하면 PostgreSQL URL은 다음처럼 조립됩니다.

```text
postgresql+asyncpg://haejillyeok:haejillyeok@localhost:5432/haejillyeok
```

실행 환경은 `local`, `dev`, `prod` 중 하나를 사용합니다. DB connection pool 값은
`app/shared/core/config/database.py`의 pool config에서 코드로 관리합니다.
DB URL은 위 접속 정보를 코드에서 조립합니다.
`be` 서버는 시작 시 SQLAlchemy async engine과 sessionmaker를 만들고,
요청 처리에서 `app.be.dependencies.database.get_db_session`을 통해 pool 기반 세션을 가져옵니다.
`agent` 서버는 DB 연결을 갖지 않습니다.

## Observability

로컬 APM 관측 인프라는 Docker Compose로 실행합니다.

```bash
mise run infra-up
```

프로젝트 디렉터리에 진입하면 mise enter hook도 같은 `infra-up` task를 실행합니다.

구성은 FastAPI 앱이 OpenTelemetry OTLP로 metric/trace를 내보내고,
OpenTelemetry Collector가 metric은 Prometheus scrape endpoint로 변환하고 trace는 Tempo에 저장한 뒤,
앱 파일 로그는 Promtail이 Loki로 전송합니다. Prometheus, Tempo, Loki, Grafana가 집계와 조회를
담당합니다.

```text
FastAPI -> OTLP HTTP :4318 -> OpenTelemetry Collector -> Prometheus / Tempo -> Grafana
FastAPI -> logs/*.log* -> Promtail -> Loki -> Grafana
```

로컬 접속 주소는 아래와 같습니다.

```text
be HTTP:              http://127.0.0.1:8000
agent HTTP:           http://127.0.0.1:8001
Grafana:              http://localhost:3000
Prometheus:           http://localhost:9090
Tempo:                http://localhost:3200
Loki:                 http://localhost:3100
OpenTelemetry HTTP:   localhost:4318
Collector metrics:    http://localhost:9464/metrics
```

서버 포트 충돌이 있거나 외부 도구가 다른 서버 포트를 바라봐야 하면 `.env` 또는 실행
환경변수로 port 값을 바꿉니다. Docker Compose 인프라 포트는 서버 `.env` 관리 대상이 아닙니다.
서버 프로세스의 기본 타임존은 KST(`Asia/Seoul`)이며, `APP_TIMEZONE=Asia/Seoul`을 앱 설정 기본값으로
사용합니다.

| Target | Default |
| --- | --- |
| be HTTP | `127.0.0.1:8000` |
| agent HTTP | `127.0.0.1:8001` |

Grafana 기본 계정은 `admin` / `admin`입니다. 필요한 경우 인프라 실행 환경에서 관리자 계정 값을
바꿉니다. Prometheus, Tempo, Loki datasource와 FastAPI metric, trace, log dashboard는 자동으로
provision 됩니다.

앱 로그와 Uvicorn access/error 로그는 stdout과 `logs/<app_name>.log`에 함께 기록합니다.
파일 로그는 매일 회전하고 기본 14일 동안 보관합니다. `logs/`의 `*.log*` 전체 용량이
`LOG_MAX_TOTAL_BYTES`를 넘으면 오래된 파일부터 삭제합니다. 기본값은 1GB입니다.

```text
LOG_FILE_ENABLED=true
LOG_DIR=logs
LOG_RETENTION_DAYS=14
LOG_MAX_TOTAL_BYTES=1073741824
LOG_CLEANUP_INTERVAL_SECONDS=60
```

Promtail은 `logs/*.log*` 파일을 읽고 log line에서 `app_name`, `level`, `logger` label을 추출해
Loki로 전송합니다. Grafana Explore의 Loki datasource에서 `{job="haejillyeok-backend"}`,
`{app_name="haejillyeok-be"}` 같은 LogQL query로 확인합니다. Grafana log dashboard는
`docker/grafana/dashboards/fastapi-logs.json`에서 provision 되며 log volume, error logs, top
logger, recent logs, error log lines, audit request logs panel을 포함합니다.

FastAPI 앱은 기본적으로 APM exporter를 연결합니다. 특정 상황에서 관측 전송을 끄고 싶을 때만
서버 `.env`의 APM exporter 값을 비활성화합니다. 기본 전송 endpoint는 `http://localhost:4318`
입니다. Collector의 host port를 바꿨다면 앱 실행 환경의 exporter endpoint도 같은 포트로 맞춥니다.

Grafana metric dashboard는 `docker/grafana/dashboards/fastapi-apm.json`에서 provision 됩니다.
주요 panel은 throughput, 5xx error rate, p95 latency, p99 latency, status별 throughput입니다.
Prometheus metric은 route template label을 사용해 `/items/{item_id}`처럼 집계하며,
개별 path parameter 값은 label에 넣지 않습니다.

객체별 실행 시간은 trace span으로 확인합니다. FastAPI 요청 span 아래에 service/repository span을
수동으로 붙이려면 `app/shared/core/observability.py`의 `@traced_method`를 사용합니다.
예를 들어 인증 흐름은 `AuthService.login_or_register`,
`AuthRepository.get_user_by_account_id`, `AuthRepository.get_user_by_nickname`,
`AuthRepository.create_user_session` 같은 child span을
Tempo에 저장합니다. Grafana trace dashboard는
`docker/grafana/dashboards/fastapi-traces.json`에서 provision 됩니다. Dashboard 이름은
`Haejillyeok FastAPI Traces`이며, request trace와 service/repository object span search panel을
포함합니다.

### Migration

DB schema migration은 Alembic으로 관리합니다. Migration 파일은 `migrations/versions/`에 두고
코드와 함께 Git으로 형상관리합니다.

#### Files

- `alembic.ini`: Alembic CLI가 읽는 프로젝트 설정입니다. Migration 디렉터리 위치만 지정하며,
  앱 로깅 설정과 겹치지 않도록 별도 logger 설정은 두지 않습니다.
- `migrations/env.py`: Alembic 실행 환경입니다. DB URL을 결정하고, SQLAlchemy metadata를 연결한 뒤
  online/offline migration을 실행합니다.
- `migrations/script.py.mako`: `alembic revision`이 새 revision 파일을 만들 때 사용하는 템플릿입니다.

#### Target DB

Migration 대상 DB는 기본적으로 앱이 쓰는 `.env` 또는 실행 환경의 DB 접속 값으로 조립한 URL입니다.
별도 migration 전용 환경 변수는 관리하지 않습니다. 특정 DB에 일회성으로 실행해야 할 때만
Alembic `-x database_url=...` 옵션을 사용합니다.

```bash
.venv/bin/python -m alembic -x database_url="postgresql+asyncpg://user:password@localhost:5432/db" upgrade head
```

#### Commands

```bash
mise run db-revision "change description"
mise run db-upgrade head
mise run db-upgrade-head
mise run db-current
mise run db-history
mise run db-downgrade -1
mise run db-downgrade-one
```

운영 환경에서는 앱 시작 중 자동으로 migration을 실행하지 않고, 배포 절차에서 앱 실행 전에
`mise run db-upgrade-head`를 실행합니다.

## Run

백엔드 서버:

```bash
mise run dev-be
```

`dev-be`는 백엔드 REST API 서버를 실행합니다.
HTTP host는 `127.0.0.1`로 고정하고, port는 서버 `.env`의 백엔드 포트 값으로 제어합니다.

에이전트 서버:

```bash
mise run dev-agent
```

`dev-agent`는 에이전트 REST API 서버를 실행합니다.
HTTP host는 `127.0.0.1`로 고정하고, port는 서버 `.env`의 에이전트 포트 값으로 제어합니다.

## Test

```bash
mise run test
```

테스트는 `pytest-cov`로 전체 `app` package coverage를 측정하며, 총 coverage가 90% 미만이면
실패합니다.

## Format

포맷은 `ruff`로 관리합니다. 변경 전 확인은 아래 명령으로 실행합니다.

```bash
mise run format-check
```

로컬에서 자동 정리가 필요하면 아래 명령을 사용합니다.

```bash
mise run format
```
