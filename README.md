# backend

## 로컬 개발 환경

이 프로젝트는 로컬 런타임과 인프라 실행을 위해 `mise`를 사용합니다.

## 문서

프로젝트 문서는 [docs/index.md](docs/index.md)에서 확인할 수 있습니다.

- FastAPI, WebSocket 가이드: [docs/backend-guidelines.md](docs/backend-guidelines.md)
- 코드 컨벤션: [docs/code-conventions.md](docs/code-conventions.md)

### mise 설정

아직 셸에 mise 활성화 설정이 없다면 아래 명령어를 실행합니다.

```bash
echo 'eval "$(mise activate zsh)"' >> ~/.zshrc
source ~/.zshrc
```

프로젝트 진입 시 실행되는 mise hook을 사용하기 위해 experimental 설정을 켜고,
현재 프로젝트 설정을 신뢰하도록 등록합니다.

```bash
mise settings set experimental true
mise trust
```

프로젝트에 설정된 Python 버전을 설치합니다.

```bash
mise install
```

### 로컬 인프라

프로젝트 디렉터리에 진입하면 mise가 `.mise.toml`의 enter hook을 실행해서
`mise run infra-up`과 같은 로컬 인프라를 자동으로 실행합니다.

```bash
cd /path/to/backend
```

인프라와 앱 명령어는 `mise run`으로 실행할 수 있습니다.

```bash
mise run infra-up
mise run infra-down
mise run infra-logs
mise run install
mise run dev-be
mise run dev-agent
mise run test
mise run format
mise run format-check
mise run db-revision "change description"
mise run db-upgrade-head
mise run db-current
mise run db-history
```

`infra-up`은 PostgreSQL, OpenTelemetry Collector, Prometheus, Tempo, Loki, Promtail, Grafana를
실행합니다.
주요 로컬 주소는 아래와 같습니다.

```text
PostgreSQL:           localhost:5432
be HTTP:              http://127.0.0.1:8000
agent HTTP:           http://127.0.0.1:8001
Grafana:              http://localhost:3000
Prometheus:           http://localhost:9090
Tempo:                http://localhost:3200
Loki:                 http://localhost:3100
OpenTelemetry HTTP:   localhost:4318
```

서버 포트가 이미 사용 중이면 `.env`의 서버 포트 값을 바꾸거나, 실행 시 같은 값을
셸 환경변수로 넘길 수 있습니다.

서버 프로세스의 기본 타임존은 KST(`Asia/Seoul`)입니다. 앱 설정 기본값도
`APP_TIMEZONE=Asia/Seoul`이며, 다른 값이 필요할 때만 `.env`나 실행 환경변수로 덮어씁니다.

Grafana 기본 계정은 `admin` / `admin`이며, FastAPI metric dashboard, trace dashboard, log dashboard,
Prometheus/Tempo/Loki datasource는 자동으로 provision 됩니다. 앱은 기본적으로 metric/trace를
내보내며, 필요한 상황에서만 서버 `.env`의 APM exporter 값을 꺼둡니다.

앱 로그와 Uvicorn access/error 로그는 stdout과 `logs/<app_name>.log`에 함께 기록됩니다.
파일 로그는 매일 회전하며 기본 14일 동안 보관하고, `logs/`의 `*.log*` 전체 용량이 기본 1GB를
넘으면 오래된 파일부터 삭제합니다.
Promtail은 `logs/*.log*`를 읽어 Loki로 전송하므로 Grafana Explore의 Loki datasource에서
`{job="haejillyeok-backend"}` 또는 `{app_name="haejillyeok-be"}`처럼 조회할 수 있습니다.
`Haejillyeok FastAPI Logs` dashboard에서는 app, level, logger, 검색어 기준으로 같은 로그를
조회합니다.
필요하면 아래 환경변수로 파일 로그 기준을 바꿉니다.

```text
LOG_FILE_ENABLED=true
LOG_DIR=logs
LOG_RETENTION_DAYS=14
LOG_MAX_TOTAL_BYTES=1073741824
LOG_CLEANUP_INTERVAL_SECONDS=60
```

백엔드 서버 실행 전 프로젝트 루트의 `.env`에 DB 접속 정보를 설정해야 합니다.
로컬 설정 예시를 사용하면 PostgreSQL URL은 다음처럼 조립됩니다.

```text
postgresql+asyncpg://haejillyeok:haejillyeok@localhost:5432/haejillyeok
```

실행 환경은 `local`, `dev`, `prod` 중 하나를 사용합니다. DB connection pool 값은
[app/shared/core/config/database.py](app/shared/core/config/database.py)에서 코드로 관리합니다.
DB URL은 위 접속 정보를 코드에서 조립합니다. DB 연결은 `be` 서버에서만 관리하며,
SQLAlchemy async engine의 connection pool을 통해 세션을 가져옵니다.

### DB 마이그레이션

DB schema migration은 Alembic으로 관리합니다.

```bash
mise run db-revision "change description"
mise run db-upgrade-head
mise run db-current
mise run db-history
mise run db-downgrade-one
```

Migration 대상 DB는 기본적으로 앱이 쓰는 `.env`의 DB 접속 값에서 조립한 URL입니다.
별도 DB용 환경 변수를 추가로 관리하지 않습니다. 일회성으로 다른 DB를 지정해야 할 때만
Alembic의 `-x database_url=...` 옵션을 직접 사용합니다.

```bash
.venv/bin/python -m alembic -x database_url="postgresql+asyncpg://user:password@localhost:5432/db" upgrade head
```

## FastAPI 실행

개발 의존성을 설치합니다.

```bash
mise run install
```

백엔드 서버를 실행합니다.

```bash
mise run dev-be
```

`dev-be`는 백엔드 REST API 서버를 실행합니다.
HTTP host는 `127.0.0.1`로 고정하고, port는 서버 `.env`의 백엔드 포트 값으로 제어합니다.

에이전트 서버를 실행합니다.

```bash
mise run dev-agent
```

`dev-agent`는 에이전트 REST API 서버를 실행합니다.
HTTP host는 `127.0.0.1`로 고정하고, port는 서버 `.env`의 에이전트 포트 값으로 제어합니다.

FastAPI 문서와 OpenAPI schema는 각 서버 실행 후 아래 경로에서 확인할 수 있습니다.

```text
Swagger UI:   GET /docs
OpenAPI JSON: GET /openapi.json
ReDoc:        GET /redoc
```

기본 헬스 체크 엔드포인트는 아래 경로에서 확인할 수 있습니다.

```text
be:    GET /health
be:    GET /api/v1/health
agent: GET /health
agent: GET /api/v1/health
```

테스트는 아래 명령으로 실행합니다.

```bash
mise run test
```

포맷은 `ruff`로 관리합니다. 변경 전 확인은 `format-check`, 로컬 자동 정리는 `format`을
사용합니다.

```bash
mise run format-check
mise run format
```

## Docker 실행

이미지는 하나로 빌드하고 Docker Hub에 push합니다. 실행할 서버와 포트는 컨테이너 실행 환경변수로
선택합니다. `DOCKERHUB_USERNAME`은 Docker Hub 계정명으로 바꿉니다.
Runtime image에는 Alembic 설정과 migration revision을 넣지 않습니다. DB migration은 앱 컨테이너
실행 전 별도 배포 단계에서 처리합니다.

```bash
docker login

DOCKERHUB_USERNAME=your-dockerhub-username
IMAGE="$DOCKERHUB_USERNAME/haejillyeok-backend"

docker build \
  -t "$IMAGE:0.1.0" \
  -t "$IMAGE:latest" \
  .

docker push "$IMAGE:0.1.0"
docker push "$IMAGE:latest"
```

Mac에서 빌드하고 Linux 서버나 여러 CPU 아키텍처에서 실행할 예정이면 `buildx`로 바로 push합니다.

```bash
DOCKERHUB_USERNAME=your-dockerhub-username
IMAGE="$DOCKERHUB_USERNAME/haejillyeok-backend"

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "$IMAGE:0.1.0" \
  -t "$IMAGE:latest" \
  --push \
  .
```

`docker run`에서는 같은 `PORT` 값을 컨테이너 환경변수와 port publishing 양쪽에 넘깁니다.
DB 비밀번호 같은 운영 secret은 image에 넣지 않고 컨테이너 실행 환경에서 주입합니다. OpenTelemetry
기본값은 `OTEL_ENABLED=true`이며, Collector를 쓰지 않는 배포에서만 `false`로 끕니다.
Collector와 같은 Docker network에서 실행할 때는 OTLP endpoint host로 Docker DNS 이름인
`otel-collector`를 사용합니다.

백엔드 서버를 실행합니다.

```bash
DOCKERHUB_USERNAME=your-dockerhub-username
IMAGE="$DOCKERHUB_USERNAME/haejillyeok-backend"
PORT=8000
DOCKER_NETWORK=backend_default
BE_ENV=prod
APP_TIMEZONE=Asia/Seoul
BE_DB_HOST=postgres.example.com
BE_DB_PORT=5432
BE_DB_USER=haejillyeok
BE_DB_PASSWORD=change-me
BE_DB_NAME=haejillyeok
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_METRIC_EXPORT_INTERVAL=5000
LOG_FILE_ENABLED=true
LOG_DIR=/app/logs
LOG_RETENTION_DAYS=14
LOG_MAX_TOTAL_BYTES=1073741824
LOG_CLEANUP_INTERVAL_SECONDS=60

docker run --rm \
  --network "$DOCKER_NETWORK" \
  -e APP_MODULE=be \
  -e APP_TIMEZONE="$APP_TIMEZONE" \
  -e PORT="$PORT" \
  -e BE_ENV="$BE_ENV" \
  -e BE_DB_HOST="$BE_DB_HOST" \
  -e BE_DB_PORT="$BE_DB_PORT" \
  -e BE_DB_USER="$BE_DB_USER" \
  -e BE_DB_PASSWORD="$BE_DB_PASSWORD" \
  -e BE_DB_NAME="$BE_DB_NAME" \
  -e OTEL_ENABLED="$OTEL_ENABLED" \
  -e OTEL_EXPORTER_OTLP_ENDPOINT="$OTEL_EXPORTER_OTLP_ENDPOINT" \
  -e OTEL_METRIC_EXPORT_INTERVAL="$OTEL_METRIC_EXPORT_INTERVAL" \
  -e LOG_FILE_ENABLED="$LOG_FILE_ENABLED" \
  -e LOG_DIR="$LOG_DIR" \
  -e LOG_RETENTION_DAYS="$LOG_RETENTION_DAYS" \
  -e LOG_MAX_TOTAL_BYTES="$LOG_MAX_TOTAL_BYTES" \
  -e LOG_CLEANUP_INTERVAL_SECONDS="$LOG_CLEANUP_INTERVAL_SECONDS" \
  -v /var/log/haejillyeok:/app/logs \
  -p "$PORT:$PORT" \
  "$IMAGE:latest"
```

에이전트 서버를 실행합니다.

```bash
DOCKERHUB_USERNAME=your-dockerhub-username
IMAGE="$DOCKERHUB_USERNAME/haejillyeok-backend"
PORT=8001
DOCKER_NETWORK=backend_default
BE_ENV=prod
APP_TIMEZONE=Asia/Seoul
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_METRIC_EXPORT_INTERVAL=5000
LOG_FILE_ENABLED=true
LOG_DIR=/app/logs
LOG_RETENTION_DAYS=14
LOG_MAX_TOTAL_BYTES=1073741824
LOG_CLEANUP_INTERVAL_SECONDS=60

docker run --rm \
  --network "$DOCKER_NETWORK" \
  -e APP_MODULE=agent \
  -e APP_TIMEZONE="$APP_TIMEZONE" \
  -e PORT="$PORT" \
  -e BE_ENV="$BE_ENV" \
  -e OTEL_ENABLED="$OTEL_ENABLED" \
  -e OTEL_EXPORTER_OTLP_ENDPOINT="$OTEL_EXPORTER_OTLP_ENDPOINT" \
  -e OTEL_METRIC_EXPORT_INTERVAL="$OTEL_METRIC_EXPORT_INTERVAL" \
  -e LOG_FILE_ENABLED="$LOG_FILE_ENABLED" \
  -e LOG_DIR="$LOG_DIR" \
  -e LOG_RETENTION_DAYS="$LOG_RETENTION_DAYS" \
  -e LOG_MAX_TOTAL_BYTES="$LOG_MAX_TOTAL_BYTES" \
  -e LOG_CLEANUP_INTERVAL_SECONDS="$LOG_CLEANUP_INTERVAL_SECONDS" \
  -v /var/log/haejillyeok:/app/logs \
  -p "$PORT:$PORT" \
  "$IMAGE:latest"
```

## GitHub Actions Docker 배포

`.github/workflows/docker-deploy.yml`은 자동 branch trigger 없이 수동 실행만 사용합니다. GitHub
Actions 화면에서 `Docker Deploy` workflow를 선택하고 `target_tag`에 배포할 Git tag를 입력한 뒤
`confirm_deploy=deploy`를 고르면 Docker Hub에 image를 push한 뒤 SSH로 원격 서버에 접속해
컨테이너를 교체합니다. `confirm_deploy=no`는 확인 job만 실행하고 배포하지 않으며, 로그에 최근 Git
tag 목록을 출력합니다.

Docker image tag는 수동 실행 input `target_tag`를 그대로 사용합니다. 예를 들어 `target_tag`가
`v1.2.3`이면 Docker Hub에는 `v1.2.3`와 `latest`를 함께 push하고, 원격 서버도 `v1.2.3` image를
pull합니다. 입력한 Git tag가 없거나 Docker image tag로 쓸 수 없는 tag이면 배포 job은 실패합니다.

GitHub Secrets:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
DEPLOY_HOST
DEPLOY_SSH_KEY
BE_DB_HOST
BE_DB_USER
BE_DB_PASSWORD
BE_DB_NAME
```

GitHub Variables:

```text
DEPLOY_SSH_PORT=22
DOCKER_NETWORK=backend_default
BE_DB_PORT=5432
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_METRIC_EXPORT_INTERVAL=5000
LOG_FILE_ENABLED=true
LOG_RETENTION_DAYS=14
LOG_MAX_TOTAL_BYTES=1073741824
LOG_CLEANUP_INTERVAL_SECONDS=60
```

Workflow가 생성하는 `.env`의 `BE_ENV`는 항상 `prod`, `APP_TIMEZONE`은 `Asia/Seoul`로
고정됩니다.
`DOCKER_NETWORK`는 원격 서버에서 OpenTelemetry Collector가 붙어 있는 user-defined Docker
network 이름입니다.
파일 로그는 원격 서버의 `/var/log/haejillyeok`에 저장합니다. 컨테이너 내부에서는 `/app/logs`로
보이도록 bind mount하며, Workflow는 컨테이너의 `app` 사용자로 쓸 수 있게 소유권을 맞춘 뒤
`docker run -v /var/log/haejillyeok:/app/logs`로 실행합니다.

배포 대상 서버는 `deploy` 계정으로 SSH 접속할 수 있어야 하고, Docker 명령을 실행할 권한이 있어야
합니다. Workflow는 원격 서버의 `/opt/haejillyeok/backend/.env`를 만들고 `docker run --env-file`로
컨테이너 환경변수에 주입합니다. `deploy` 계정은 `/opt/haejillyeok/backend`에 쓸 수 있어야 합니다.
Runtime image에는 `.env`, Alembic 설정, migration revision을 넣지 않습니다.

```bash
./
├── app
│   ├── __init__.py
│   ├── main.py
│   ├── agent
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api
│   │   │   ├── __init__.py
│   │   │   ├── router.py
│   │   │   └── endpoints
│   │   │       ├── __init__.py
│   │   │       └── health.py
│   │   ├── dependencies
│   │   │   ├── __init__.py
│   │   │   └── services.py
│   │   └── services
│   │       ├── __init__.py
│   │       ├── v1
│   │       │   └── __init__.py
│   │       └── v2
│   │           └── __init__.py
│   ├── be
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api
│   │   │   ├── __init__.py
│   │   │   ├── router.py
│   │   │   └── endpoints
│   │   │       ├── __init__.py
│   │   │       └── health.py
│   │   ├── dependencies
│   │   │   ├── __init__.py
│   │   │   ├── database.py
│   │   │   └── services.py
│   │   ├── repository
│   │   │   ├── __init__.py
│   │   │   └── base.py
│   │   ├── schemas
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── request
│   │   │   │   └── __init__.py
│   │   │   └── response
│   │   │       ├── __init__.py
│   │   │       └── health.py
│   │   └── services
│   │       ├── __init__.py
│   │       ├── v1
│   │       │   └── __init__.py
│   │       └── v2
│   │           └── __init__.py
│   ├── shared
│   │   ├── __init__.py
│   │   ├── clients
│   │   │   └── __init__.py
│   │   ├── core
│   │   │   ├── __init__.py
│   │   │   ├── config
│   │   │   │   ├── __init__.py
│   │   │   │   ├── app.py
│   │   │   │   └── database.py
│   │   │   └── logging_config.py
├── docs
│   ├── api.md
│   ├── architecture.md
│   └── development.md
├── pyproject.toml
└── test
    ├── __init__.py
    └── test_app.py
```
