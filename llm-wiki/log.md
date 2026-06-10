# LLM Wiki Log

이 파일은 `llm-wiki/`의 시간순 작업 이력입니다. 새 항목은 위에 추가합니다.

## [2026-06-10] maintenance | Use Docker env-file for deploy env

- GitHub Actions Docker deploy workflow가 원격 `.env`를 `/app/.env:ro`로 마운트하지 않고 `docker run --env-file`로 주입하도록 바꿨다.
- 원격 `.env`는 `chmod 600`을 유지해 `deploy` 계정만 읽고, 컨테이너 내부 `app` 유저가 bind mount 권한 때문에 `.env`를 읽지 못하는 문제를 피한다.
- README와 runtime configuration wiki에 Docker 배포 env 주입 방식을 반영했다.

## [2026-06-10] maintenance | Restrict CORS origin allowlist

- CORS middleware 적용 대상을 브라우저에서 직접 호출되는 `be` 서버로 제한했다.
- 허용 origin은 `http://localhost:3000`, `https://haejillyeok.com`, `https://agent.haejillyeok.com`, `https://www.haejillyeok.com`이다.
- `agent` 서버는 `be`에서 서버 간 HTTP로 호출하므로 CORS를 등록하지 않고, 접근 제한은 네트워크/인증 계층에서 다룬다고 기록했다.

## [2026-06-10] maintenance | Keep migration tunnel port internal

- DB migration GitHub Actions workflow에서 `MIGRATION_LOCAL_DB_PORT` 사용자 설정값을 제거했다.
- SSH 터널 runner 측 포트는 workflow 내부 값 `15432`로 고정하고, 사용자가 관리할 DB 변수는 private DB endpoint와 port만 남겼다.
- `database-migrations.md`, `runtime-configuration.md`에서 선택 GitHub Variables 목록을 갱신했다.

## [2026-06-10] maintenance | Add SSH-tunneled DB migration workflow

- `.github/workflows/db-migration.yml`을 추가해 GitHub Actions 수동 실행으로 운영 DB migration 작업을 선택 실행할 수 있게 했다.
- Workflow는 `deploy` SSH 인스턴스에 로컬 포워딩을 열고 private subnet DB에 접근한 뒤 `mise` DB task를 실행한다.
- 기본 작업은 `db-upgrade-head`이며, `db-current`, `db-history`, `db-upgrade`, `db-downgrade`, `db-downgrade-one`을 선택할 수 있다.
- 운영 DB migration 기준과 필요한 GitHub Secrets/Variables를 `database-migrations.md`, `runtime-configuration.md`에 반영했다.

## [2026-06-10] maintenance | Select deploy Git tag manually

- GitHub Actions Docker deploy workflow에 `target_tag` 수동 입력을 추가했다.
- `confirm_deploy=no` 실행은 최근 Git tag 목록을 출력해 배포 전 태그 조회용으로 사용할 수 있게 했다.
- 배포 job은 입력한 tag가 실제 commit tag이고 Docker image tag 형식에 맞는지 검증한 뒤 해당 tag ref를 checkout해 build/push/deploy한다.
- README와 runtime configuration wiki에서 최신 tag 자동 선택 기준을 수동 tag 선택 기준으로 바꿨다.

## [2026-06-09] maintenance | Move deploy env path under opt

- GitHub Actions Docker deploy workflow의 원격 배포 디렉터리를 `/opt/haejillyeok/backend`로 바꿨다.
- README와 runtime configuration wiki에 `deploy` 계정의 `/opt/haejillyeok/backend` 쓰기 권한 필요성을 명시했다.

## [2026-06-09] maintenance | Use Docker DNS for OTLP endpoint

- GitHub Actions Docker deploy workflow의 `OTEL_EXPORTER_OTLP_ENDPOINT` 기본값을 `http://otel-collector:4318`로 바꿨다.
- 배포 컨테이너가 `DOCKER_NETWORK` user-defined Docker network에 붙도록 하고, 기본값을 `backend_default`로 정리했다.
- README와 runtime/observability wiki에 Docker network 기반 OTLP endpoint 기준을 반영했다.

## [2026-06-09] maintenance | Set OTEL_ENABLED default to true

- GitHub Actions Docker deploy workflow의 `OTEL_ENABLED` 기본값을 `true`로 바꿨다.
- README와 runtime configuration wiki에서 OpenTelemetry 기본값을 `true`로 정리했다.

## [2026-06-09] maintenance | Fix deploy BE_ENV to prod

- GitHub Actions Docker deploy workflow가 생성하는 `.env`에서 `BE_ENV`를 GitHub Variable이 아니라 `prod`로 고정했다.
- README와 runtime configuration wiki에서 `BE_ENV`를 GitHub Variables 목록에서 제거했다.

## [2026-06-09] maintenance | Use Git version tag for Docker image tag

- GitHub Actions Docker deploy workflow에서 image tag를 `github.sha` 대신 선택한 ref가 도달할 수 있는 최신 Git tag로 결정하도록 바꿨다.
- Docker Hub에는 Git version tag와 `latest`를 함께 push하고, SSH 배포는 Git version tag image를 pull하도록 했다.
- Git tag가 없거나 Docker image tag 형식에 맞지 않으면 배포 job이 실패하도록 했다.

## [2026-06-09] maintenance | Add manual GitHub Actions Docker deploy

- `.github/workflows/docker-deploy.yml`을 추가해 `workflow_dispatch` 수동 실행만으로 Docker build/push/SSH deploy를 실행하도록 했다.
- `confirm_deploy` input이 `deploy`일 때만 실제 배포 job을 실행하고, 기본값 `no`는 확인 job만 실행한다.
- Runner에서 Docker Hub에 image를 push하고, 원격 서버에는 `deploy` 계정 SSH로 접속해 `/opt/haejillyeok/backend/.env`를 만들고 `/app/.env:ro` volume으로 마운트한다.
- 원격 서버는 Docker Hub credential 없이 public image를 pull하고, 컨테이너는 기본 `APP_MODULE=be`, `PORT=8000`으로 실행한다.

## [2026-06-09] maintenance | Document Docker runtime environment variables

- 공개 runtime image에는 `.env`를 포함하지 않으므로 `docker run`에서 필요한 환경변수를 주입한다고 README에 명시했다.
- be 실행 예시에 `BE_ENV`, `BE_DB_*`, `OTEL_*`, `APP_MODULE=be`, `PORT` 주입을 추가했다.
- agent 실행 예시에 `APP_MODULE=agent`, `BE_ENV`, `OTEL_*`, `PORT` 주입을 추가했다.
- Shell에서 그대로 복사 가능한 예시가 되도록 angle bracket placeholder 대신 일반 예시값을 사용했다.

## [2026-06-09] maintenance | Simplify Docker app module selector

- `APP_MODULE` Docker 환경변수는 전체 ASGI import string이 아니라 `be` 또는 `agent` 값만 받도록 바꿨다.
- `Dockerfile`은 Uvicorn 실행 대상을 `app.${APP_MODULE}.main:app` 형태로 조립한다.
- README의 agent 실행 예시를 `APP_MODULE=agent`로 갱신했다.

## [2026-06-09] maintenance | Exclude migrations from runtime Docker image

- Runtime Docker image에서 migration을 실행하지 않기로 하고 `Dockerfile`에서 `alembic.ini`와 `migrations/` 복사를 제거했다.
- `.dockerignore`에 `alembic.ini`와 `migrations/`를 추가해 build context에서도 제외했다.
- Alembic은 runtime dependency가 아니라 dev optional dependency로 옮겨 로컬 `mise run db-*` 절차에서만 사용하도록 했다.

## [2026-06-09] maintenance | Remove Python cache files from Docker image

- `.dockerignore`에 nested `__pycache__/`와 `*.pyc` 제외 규칙을 추가했다.
- `Dockerfile`에서 copy 이후 `/app` 아래 Python bytecode/cache 파일을 삭제해 runtime image에 남지 않도록 했다.
- 공개 Docker image에는 local secret, local path, Python cache 산출물이 들어가지 않아야 한다는 기준을 유지했다.

## [2026-06-09] maintenance | Use Docker Hub image tags in README

- Docker build 예시를 로컬 이미지명 대신 Docker Hub 계정명 기반 tag로 바꿨다.
- `0.1.0`과 `latest` tag를 함께 붙이고 Docker Hub에 push하는 명령을 README에 추가했다.
- Mac에서 빌드해 Linux 서버나 여러 CPU 아키텍처에서 실행할 때는 `docker buildx build --platform linux/amd64,linux/arm64 --push`를 사용한다고 기록했다.

## [2026-06-09] maintenance | Document Docker PORT to PORT publishing

- `docker run` 예시는 shell `PORT` 값을 `-e PORT="$PORT"`와 `-p "$PORT:$PORT"`에 함께 넘기도록 README에 추가했다.
- be 서버는 기본 `APP_MODULE`을 사용하고 `PORT=8000`을 넘기며, agent 서버는 `APP_MODULE=app.agent.main:app`, `PORT=8001`을 넘기는 기준을 남겼다.

## [2026-06-09] maintenance | Add environment-selected Docker runtime

- 루트 `Dockerfile`을 추가해 `python:3.11-slim` 기반 runtime image를 만들도록 했다.
- 기본 실행 대상은 `APP_MODULE=app.be.main:app`, `PORT=8000`인 be 서버로 두고, 환경변수로 `APP_MODULE=app.agent.main:app`, `PORT=8001`을 주입하면 agent 서버를 같은 image에서 실행할 수 있게 했다.
- 컨테이너 port publishing을 위해 Uvicorn 기본 host는 `0.0.0.0`으로 두고, worker 수는 `WORKERS` 환경변수로 제어한다고 기록했다.

## [2026-06-09] maintenance | Add Docker build context ignore rules

- 공개 Docker image build context에 `.env`, `.env.*`, 로컬 도구 상태, 가상환경, 테스트/coverage/build 산출물, runtime artifact를 포함하지 않도록 `.dockerignore`를 추가했다.
- 사람용 문서, AI용 `llm-wiki/`, 테스트 코드는 runtime image에 필요하지 않은 대상으로 제외한다고 기록했다.
- 운영 secret은 image에 bake하지 않고 컨테이너 실행 환경에서 주입한다는 기준을 남겼다.

## [2026-06-09] maintenance | Run infra-up from mise enter hook

- `.mise.toml`의 enter hook이 `mise run infra-up`을 실행하도록 바꿨다.
- 프로젝트 디렉터리 진입 시 PostgreSQL뿐 아니라 OpenTelemetry Collector, Prometheus, Tempo, Grafana도 함께 시작된다고 기록했다.

## [2026-06-09] maintenance | Update auth account input rules

- PoC 인증 기준을 닉네임 로그인에서 계정 ID 기반 로그인으로 갱신했다.
- 계정 ID는 영어 문자, 숫자, `_`만 허용하고 3~20자로 제한한다고 정리했다.
- 닉네임은 한글, 영어, 숫자, `_`만 허용하고 3~20자로 제한한다고 정리했다.
- 비밀번호는 8~20자로 제한하고 PBKDF2-HMAC-SHA256 저장 기준은 유지한다고 남겼다.
- `users.users.account_id`를 unique, not null 로그인 식별자로 관리한다고 기록했다.

## [2026-06-08] maintenance | Add environment-controlled runtime ports

- HTTP 개발 서버는 host를 `127.0.0.1`로 고정하고 서버 `.env`의 port 값만 제어한다.
- gRPC 서버는 host를 `localhost`로 고정하고 서버 `.env`의 port 값만 제어한다.
- Docker Compose 인프라 host port는 서버 `.env` 관리 대상에서 제외한다고 정리했다.
- 앱은 기본적으로 APM exporter를 연결하고, 특정 상황에서만 서버 `.env` 값으로 비활성화한다는 기준을 남겼다.

## [2026-06-06] maintenance | Add centralized error codes and Swagger error examples

- 공개 error code를 `app/shared/core/error_codes.py`의 `ErrorCode` enum에서 관리하도록 정리했다.
- `ErrorDefinition` catalog가 error type, HTTP status, gRPC status, WebSocket close code를 함께 관리하도록 확장했다.
- Swagger 실패 응답은 `ErrorResponse` schema와 endpoint별 example/examples를 함께 표시하도록 `error_response(...)`, `error_responses(...)`, `error_example(...)` helper 기준을 추가했다.
- endpoint는 `error_responses_by_status(codes=[...])`로 error code 목록을 넘겨 HTTP status별 Swagger responses를 자동 생성하도록 정리했다.
- BE auth login의 `401`, `422` 실패 응답에 실제 application error code example을 노출했다.
- 성공 응답에는 `error` 필드를 넣지 않도록 `SuccessResponse[T]`를 도입하고, error example의 `data: null`, `details: null`은 OpenAPI 후처리로 복원하도록 정리했다.
- 일반 Swagger 문구 고정 테스트는 추가하지 않고, shared error code/helper 동작과 기존 endpoint runtime 응답 테스트를 유지했다.

## [2026-06-05] maintenance | Add request audit logging

- HTTP/gRPC 요청의 시작, 완료, 실패를 `audit.request` logger로 남기는 AOP 관측 기준을 정리했다.
- 공통 감사 이벤트 포맷은 `app/shared/core/audit.py`에 두고, HTTP middleware와 gRPC interceptor가 같은 포맷을 쓰도록 기록했다.
- payload, password, session token, cookie, authorization header는 감사 로그에 남기지 않는 privacy rule을 남겼다.

## [2026-06-05] maintenance | Add common protocol response and exceptions

- HTTP/gRPC 같은 프로토콜 경계에서 쓰는 `success`, `data`, `error` 공통 response envelope를 `app/shared/core` 기준으로 정리했다.
- 커스텀 예외는 `AppException` 기준으로 관리하고 각 프로토콜 handler에서 변환한다고 기록했다.
- BE `/api/v1/*`는 shared envelope를 HTTP JSON으로 반환하고, root `/health`는 운영 probe 용도이므로 raw response를 유지한다고 남겼다.

## [2026-06-05] maintenance | Add format check management

- 개발 의존성에 `ruff`를 추가했다.
- `mise run format`과 `mise run format-check` 태스크로 포맷 적용과 확인을 분리했다.
- README, 개발 문서, 코드 컨벤션, AI용 현재 상태 위키에 포맷 관리 기준을 반영했다.

## [2026-06-05] maintenance | Relax Swagger metadata testing rule

- 일반 Swagger 표시용 `summary`, 설명 문구, 단순 `operation_id`는 전용 OpenAPI schema 테스트로 고정하지 않기로 정리했다.
- `test_be_openapi_has_stable_swagger_metadata` 테스트를 제거했다.
- OpenAPI schema 테스트는 프론트 SDK 자동 생성, CI schema diff, breaking change 감지처럼 schema 자체가 제품 계약일 때만 추가한다고 남겼다.

## [2026-06-05] maintenance | Add OpenAPI Swagger metadata guide

- `llm-wiki/wiki/openapi-swagger.md`에 FastAPI OpenAPI schema와 Swagger UI 운영 기준을 추가했다.
- public HTTP endpoint는 `response_model`, `status_code`, `summary`, `operation_id`, 주요 실패 `responses`를 명시한다고 정리했다.
- OpenAPI Generator나 프론트 client 생성을 대비해 `operation_id`를 안정적인 snake_case 이름으로 고정하는 기준을 남겼다.
- BE auth/health endpoint의 Swagger metadata를 OpenAPI schema 테스트로 고정했다.

## [2026-06-06] maintenance | Add Tempo object-level tracing

- OpenTelemetry trace pipeline을 debug exporter뿐 아니라 Tempo로도 전달하도록 Docker Compose와 Collector 설정을 확장했다.
- Grafana에 Tempo datasource와 `Haejillyeok FastAPI Traces` dashboard를 provision하고, 객체별 실행 시간은 trace table과 waterfall에서 확인하도록 정리했다.
- `app/shared/core/observability.py`에 `@traced_method` helper를 추가하고 인증 service/repository 경계에 child span을 붙였다.
- span attribute에는 객체명, 계층, 코드 namespace/function만 넣고 payload, token, cookie 같은 민감값은 넣지 않는 기준을 남겼다.

## [2026-06-06] maintenance | Add local APM observability stack

- FastAPI 앱은 `app/shared/core/observability.py`에서 OpenTelemetry trace instrumentation과 HTTP metric middleware를 등록한다고 정리했다.
- OpenTelemetry Collector, Prometheus, Grafana를 Docker Compose 로컬 인프라로 추가했다.
- Grafana는 provisioned Prometheus datasource와 `fastapi-apm.json` dashboard로 throughput, 5xx error rate, p95, p99 latency를 시각화한다.
- route label은 실제 path가 아니라 FastAPI route template을 사용해 metric cardinality를 낮춘다고 기록했다.

## [2026-06-09] maintenance | Remove application gRPC

- `be`와 `agent` 서버에서 gRPC 서버, proto 계약, proto 생성 태스크를 제거하기로 정리했다.
- 서버 간 통신 기준을 gRPC에서 HTTP API와 기능별 client wrapper로 바꿨다.
- OpenTelemetry exporter 기본 전송을 OTLP HTTP `http://localhost:4318`로 바꿨다.
- 공통 예외와 error definition은 HTTP status와 WebSocket close code만 관리한다고 기록했다.

## [2026-06-05] maintenance | Add auth session login decision

- 가입 겸 로그인 API는 `POST /api/v1/auth/login` 하나로 처리한다고 정리했다.
- 닉네임이 없으면 가입하고, 있으면 비밀번호를 검증하는 PoC 인증 흐름을 기록했다.
- 성공 시 opaque session token을 `session_token` HttpOnly cookie로 발급하고 DB에는 `token_hash`를 저장한다고 결정했다.
- `users.user_sessions` table의 역할과 멀티 서버 확장 기준을 위키에 남겼다.

## [2026-06-05] maintenance | Use domain schema for users

- PostgreSQL schema namespace는 프로젝트명이 아니라 도메인 기준으로 관리한다고 정리했다.
- 유저 도메인은 `users` schema를 사용하고, 유저 테이블은 `users.users`로 관리한다고 기록했다.
- ORM 모델은 `__table_args__`로 schema를 명시하고 migration은 domain schema를 생성한 뒤 table을 만들도록 기준을 남겼다.

## [2026-06-05] maintenance | Add users external identifier

- `users.public_id`를 UUID v7 외부용 관리번호로 두고 `users.id`는 내부 join용 관리번호로 유지한다고 정리했다.
- PoC 유저 테이블 결정 기록에서 외부 응답/API 식별자는 `public_id`, 내부 참조는 `id`를 사용하도록 갱신했다.

## [2026-06-05] maintenance | Add PoC users table decision

- PoC 유저 테이블 결정을 `llm-wiki/wiki/decisions/2026-06-05-users-table-poc.md`에 추가했다.
- `users.id`는 UUID v7 내부용 관리번호로 두고 외부용 관리번호는 현재 만들지 않기로 정리했다.
- 닉네임은 `text` column과 코드 단 15자 제한으로 관리하고, 비밀번호는 PBKDF2-HMAC-SHA256 hash로 저장한다고 기록했다.

## [2026-06-05] maintenance | Add database schema conventions

- `llm-wiki/wiki/database-schema-conventions.md`를 추가했다.
- UUID는 v7을 사용하고, PostgreSQL 문자열은 기본적으로 `text`를 사용하도록 정리했다.
- 외부 노출이 필요한 경우에만 외부용 관리번호를 두고, join과 foreign key는 내부용 관리번호를 기준으로 한다는 규칙을 남겼다.
- DB migration 작업 전 schema 규칙을 확인하도록 `database-migrations.md`와 `index.md`에 연결했다.

## [2026-06-05] maintenance | Clarify Alembic commands and target DB

- Alembic logger 설정을 제거해 앱 로깅 설정과 겹칠 여지를 줄였다.
- migration 대상 DB는 기본적으로 앱과 같은 DB 접속 설정을 쓰고, 일회성 override만 Alembic `-x database_url=...`로 하도록 정리했다.
- `mise` DB migration 태스크 이름과 사용법을 위키에 반영했다.
- 별도 migration 설정 테스트는 제거했다.

## [2026-06-05] maintenance | Add Alembic migration knowledge

- DB schema migration을 Alembic으로 관리하는 기준을 `llm-wiki/wiki/database-migrations.md`에 정리했다.
- `app/be/models/`를 SQLAlchemy ORM 모델과 Alembic metadata base 위치로 기록했다.
- `migrations/`를 Alembic 환경과 revision 파일 위치로 기록했다.
- 앱 시작 시 migration을 자동 실행하지 않고 배포 절차에서 앱 실행 전에 `alembic upgrade head`를 실행하는 운영 기준을 남겼다.

## [2026-06-05] maintenance | Treat docs as human-only and llm-wiki as AI knowledge

- `docs/`를 사람이 보는 문서로 재정의했다.
- `llm-wiki/`를 AI가 작업할 때 사용하는 전체 지식 레이어로 재정의했다.
- FastAPI/gRPC/WebSocket 가이드라인과 코드 컨벤션의 작업용 본문을 `llm-wiki/wiki/`에 추가했다.
- `AGENTS.md`의 구현 전 참조 대상을 `docs/`에서 `llm-wiki/`로 바꿨다.

## [2026-06-05] maintenance | Korean comment and docstring rules

- `docs/code-conventions.md`에 로직 설명과 함수 docstring을 한국어로 작성하는 규칙을 추가했다.
- public 함수, service/repository 메서드, gRPC handler, WebSocket connection manager 메서드에는 의도, 입력, 반환값, 부작용을 설명하도록 정리했다.
- 복잡한 분기, 비즈니스 규칙, timeout/cancellation, transaction, retry/compensation 로직에는 이유 중심의 한국어 주석을 남기도록 했다.
- `AGENTS.md`와 AI용 `backend-guidelines-summary.md`에도 같은 기준을 반영했다.

## [2026-06-05] ingest | Backend framework and code conventions

- `docs/index.md`를 만들어 사람용 문서 입구를 추가했다.
- `docs/backend-guidelines.md`에 사람이 읽는 FastAPI, gRPC, WebSocket 설명을 정리했다.
- `docs/code-conventions.md`에 사람이 읽는 Python 코드 스타일과 레이어 책임 설명을 정리했다.
- `README.md`와 `AGENTS.md`에서 새 문서를 참조하도록 연결했다.
- AI용 요약과 결정 기록을 `llm-wiki/wiki/`에 추가했다.

## [2026-06-05] maintenance | Clarify docs and LLM Wiki roles

- `docs/`는 사람이 보는 문서로 정의했다.
- `llm-wiki/`는 AI가 작업할 때 사용하는 지식 레이어로 정의했다.
- `docs/`에만 있는 내용이 AI 작업에도 필요하면 `llm-wiki/`에도 정리한다는 규칙을 `AGENTS.md`와 결정 기록에 추가했다.

## [2026-06-05] maintenance | LLM Wiki bootstrap

- 루트 `AGENTS.md`에 Karpathy 4원칙과 LLM Wiki 운영 규칙을 추가했다.
- `llm-wiki/index.md`를 콘텐츠 카탈로그로 만들었다.
- `llm-wiki/wiki/` 아래에 현재 상태, 프로젝트 맵, 개념, 결정, 출처 페이지를 추가했다.
- 향후 LLM은 위키를 읽거나 갱신할 때 `llm-wiki/index.md`를 먼저 확인하고, 변경 이력을 이 파일에 남긴다.
