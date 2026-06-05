# LLM Wiki Log

이 파일은 `llm-wiki/`의 시간순 작업 이력입니다. 새 항목은 위에 추가합니다.

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
- migration 대상 DB는 기본적으로 앱과 같은 `BE_DB_*` 설정을 쓰고, 일회성 override만 Alembic `-x database_url=...`로 하도록 정리했다.
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
