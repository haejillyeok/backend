# backend

## 로컬 개발 환경

이 프로젝트는 로컬 런타임과 인프라 실행을 위해 `mise`를 사용합니다.

## 문서

프로젝트 문서는 [docs/index.md](/Users/723poil/Documents/git/haejillyeok/backend/docs/index.md)에서 확인할 수 있습니다.

- FastAPI, gRPC, WebSocket 가이드: [docs/backend-guidelines.md](/Users/723poil/Documents/git/haejillyeok/backend/docs/backend-guidelines.md)
- 코드 컨벤션: [docs/code-conventions.md](/Users/723poil/Documents/git/haejillyeok/backend/docs/code-conventions.md)

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
pgvector를 포함한 PostgreSQL을 자동으로 실행합니다.

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
mise run grpc-generate
mise run test
mise run format
mise run format-check
mise run db-revision "change description"
mise run db-upgrade-head
mise run db-current
mise run db-history
```

`infra-up`은 PostgreSQL, OpenTelemetry Collector, Prometheus, Grafana를 실행합니다.
주요 로컬 주소는 아래와 같습니다.

```text
PostgreSQL:           localhost:5432
Grafana:              http://localhost:3000
Prometheus:           http://localhost:9090
Tempo:                http://localhost:3200
OpenTelemetry gRPC:   localhost:4317
OpenTelemetry HTTP:   localhost:4318
```

Grafana 기본 계정은 `admin` / `admin`이며, FastAPI metric dashboard, trace dashboard,
Prometheus/Tempo datasource는 자동으로 provision 됩니다.

백엔드 서버 실행 전 프로젝트 루트의 `.env`에 DB 접속 정보를 설정해야 합니다.
로컬 설정 예시를 사용하면 PostgreSQL URL은 다음처럼 조립됩니다.

```text
postgresql+asyncpg://haejillyeok:haejillyeok@localhost:5432/haejillyeok
```

실행 환경은 `local`, `dev`, `prod` 중 하나를 사용합니다. DB connection pool 값은
[app/shared/core/config/database.py](/Users/723poil/Documents/git/haejillyeok/backend/app/shared/core/config/database.py)에서 코드로 관리합니다.
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

Migration 대상 DB는 기본적으로 앱이 쓰는 `.env`와 `BE_DB_*` 환경 변수에서 조립한 URL입니다.
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

`dev-be`는 REST API와 `be` gRPC 서버를 함께 실행합니다.

에이전트 서버를 실행합니다.

```bash
mise run dev-agent
```

`dev-agent`는 REST API와 `agent` gRPC 서버를 함께 실행합니다.

`dev-be`, `dev-agent`, `test`는 실행 전에 proto Python binding을 자동 생성합니다.
필요할 때 직접 다시 생성할 수도 있습니다.

```bash
mise run grpc-generate
```

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

내부 gRPC 헬스 체크 계약은 각 서버의 proto 디렉터리에서 관리합니다.

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
