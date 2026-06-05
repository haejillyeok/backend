# backend

## 로컬 개발 환경

이 프로젝트는 로컬 런타임과 인프라 실행을 위해 `mise`를 사용합니다.

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
mise run test
```

PostgreSQL은 `localhost:5432`에서 실행됩니다.

백엔드 서버 실행 전 프로젝트 루트의 `.env`에 DB 접속 정보를 설정해야 합니다.
로컬 설정 예시를 사용하면 PostgreSQL URL은 다음처럼 조립됩니다.

```text
postgresql+asyncpg://haejillyeok:haejillyeok@localhost:5432/haejillyeok
```

실행 환경은 `local`, `dev`, `prod` 중 하나를 사용합니다. DB connection pool 값은
[app/shared/core/config/database.py](/Users/723poil/Documents/git/haejillyeok/backend/app/shared/core/config/database.py)에서 코드로 관리합니다.
DB URL은 위 접속 정보를 코드에서 조립합니다. DB 연결은 `be` 서버에서만 관리하며,
SQLAlchemy async engine의 connection pool을 통해 세션을 가져옵니다.

## FastAPI 실행

개발 의존성을 설치합니다.

```bash
mise run install
```

백엔드 서버를 실행합니다.

```bash
mise run dev-be
```

에이전트 서버를 실행합니다.

```bash
mise run dev-agent
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
