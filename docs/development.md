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
