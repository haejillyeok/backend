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

Migration 대상 DB는 기본적으로 앱이 쓰는 `.env` 또는 환경 변수의 `BE_DB_*` 값으로 조립한 URL입니다.
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

`dev-be`는 REST API와 `be` gRPC 서버를 함께 실행합니다.

에이전트 서버:

```bash
mise run dev-agent
```

`dev-agent`는 REST API와 `agent` gRPC 서버를 함께 실행합니다.

`dev-be`, `dev-agent`, `test`는 실행 전에 proto Python binding을 자동 생성합니다.
필요할 때 직접 다시 생성할 수도 있습니다.

```bash
mise run grpc-generate
```

## Test

```bash
mise run test
```
