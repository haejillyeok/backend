# LLM Wiki Log

이 파일은 `llm-wiki/` 정보 자체의 시간순 변경 이력입니다. 새 항목은 위에 추가합니다.
코드 변경 상세는 Git history, PR, issue에서 확인하고, 이 파일에는 위키 페이지의 지식, 계약, 정책,
컨벤션이 어떻게 바뀌었는지만 남깁니다.

## [2026-06-11] implementation | Integrate Qdrant Agent MVP

- 별도 Agent 작업공간의 끝말잇기 MVP를 monorepo `app/agent` 소유 구조로 이식했다.
- Qdrant repository, game handler, 후보 선택, 멱등성, 비동기 적재와 사용 횟수 갱신 계층을 추가했다.
- 프롬프트는 `.txt`가 아닌 `app/agent/prompts.py` 변수로 관리한다.
- 단일 Docker image에서 `APP_MODULE=agent`, `PORT=8001`로 실행하도록 k3s manifest를 추가했다.
- Qdrant local PV와 vLLM 단일 GPU replica, 모델 hostPath, `enableServiceLinks=false`를 배포 기준으로 고정했다.
- 회사 NodePort `31080`에서 Azure localhost로 이어지는 SSH reverse tunnel과 Azure Nginx를 외부 연결 경계로 기록했다.
- Agent API, 한국어 처리, Qdrant 중복 적재, k3s manifest 테스트를 추가했다.

## [2026-06-10] maintenance | Add Loki log dashboard
=======
## [2026-06-11] maintenance | Separate socket router from API router

- `realtime-websocket.md`에 WebSocket endpoint는 REST API router 밖의 `/ws/realtime`, 문서 페이지는 `/ws-docs`로 둔다는 계약을 반영했다.
- `backend-guidelines.md`에 WebSocket route는 `/ws/{feature}` 형식으로 통일하고 `app/{server}/api/socket_router.py`에서 조립한다는 기준을 정리했다.

## [2026-06-11] maintenance | Add registered route guard policy

- `backend-guidelines.md`에 등록된 HTTP route path만 통과시키고 미등록 path는 감사 로그 전에 body 없는 `404`로 차단하는 기준을 추가했다.
- route guard가 차단한 path는 Uvicorn access log에서도 필터링한다는 로그 노이즈 관리 기준을 남겼다.
- `/docs`, `/redoc`, `/openapi.json`은 등록된 문서 route로 계속 열어두는 기준을 명시했다.

## [2026-06-11] maintenance | Add commit message convention

- `code-conventions.md`에 `<type>: <english summary>` 형식의 한 줄 영어 커밋 메시지 기준을 추가했다.
- 허용 type과 summary 작성 규칙을 AI 작업용 컨벤션으로 정리했다.

## [2026-06-11] lint | Clarify LLM Wiki scope and log policy

- `llm-wiki/wiki/llm-wiki-maintenance.md`를 추가해 위키에 남길 정보와 남기지 않을 코드 변경 이력의 경계를 명시했다.
- 과거 `log.md` 항목을 코드 변경 상세가 아니라 위키 지식 변경 단위로 압축했다.
- `llm-wiki/index.md`와 `AGENTS.md`에 `log.md`를 코드 변경 로그로 쓰지 않는 기준을 연결했다.

## [2026-06-11] maintenance | Add realtime WebSocket contract knowledge

- `realtime-websocket.md`에 BE realtime WebSocket endpoint, JSON envelope, `ping`/`realtime.pong`, validation close code 기준을 정리했다.
- WebSocket 전용 문서 원본과 API-served docs route를 함께 갱신해야 한다는 문서 관리 기준을 남겼다.

## [2026-06-10] maintenance | Consolidate observability and logging knowledge

- `observability-stack.md`에 OpenTelemetry, Prometheus, Tempo, Loki, Promtail, Grafana의 데이터 흐름과 dashboard 기준을 통합했다.
- 파일 로그, Uvicorn 로그 연결, log rotation/retention, Promtail label 추출, Loki/Grafana 조회 기준을 현재 운영 규칙으로 정리했다.
- metric label cardinality, trace span attribute, 민감값 제외 기준을 관측 작업의 재사용 지식으로 남겼다.

## [2026-06-10] maintenance | Consolidate runtime and deployment configuration knowledge

- `runtime-configuration.md`에 KST 서버 타임존, CORS allowlist, Docker runtime, Docker Hub image tag, 배포 `.env`, 로그 디렉터리, Docker network 기반 OTLP endpoint 기준을 통합했다.
- GitHub Actions Docker 배포와 운영 DB migration workflow는 실행 절차가 아니라 앞으로 따라야 할 runtime/deployment 계약으로 요약했다.
- `database-migrations.md`에는 SSH tunnel 기반 운영 DB migration 기준과 concurrency/confirmation 규칙을 반영했다.

## [2026-06-09] maintenance | Replace application gRPC knowledge with HTTP boundary

- `decisions/2026-06-09-remove-application-grpc.md`에 애플리케이션 gRPC를 제거하고 FastAPI HTTP와 기능별 client wrapper를 서버 간 통신 기준으로 삼는 결정을 남겼다.
- gRPC status 기준은 HTTP status와 WebSocket close code 기준으로 대체되었음을 관련 결정 문서에 표시했다.

## [2026-06-09] maintenance | Update auth account and runtime port rules

- 인증 PoC 기준을 계정 ID 기반 가입 겸 로그인 흐름으로 갱신하고 `users.users.account_id`를 로그인 식별자로 관리하도록 정리했다.
- 서버 HTTP host/port, Docker Compose 인프라 port, OpenTelemetry 기본 활성화 기준을 runtime 지식으로 정리했다.

## [2026-06-06] maintenance | Add API error and OpenAPI operation rules

- `openapi-swagger.md`에 public HTTP endpoint의 `response_model`, `status_code`, `summary`, `operation_id`, 실패 응답 문서화 기준을 정리했다.
- 공통 response envelope, `AppException`, error code catalog, Swagger error example 기준을 API 계약 지식으로 남겼다.
- Swagger 표시 문구와 schema 테스트를 언제 고정할지에 대한 테스트 기준을 정리했다.

## [2026-06-05] maintenance | Add database and user identity knowledge

- `database-schema-conventions.md`와 `database-migrations.md`에 UUID v7, PostgreSQL `text`, 내부/외부 관리번호, Alembic migration 운영 기준을 정리했다.
- 유저 도메인은 `users` schema를 사용하고, 내부 join 식별자와 외부 노출 식별자를 분리한다는 결정을 남겼다.
- PoC 유저 테이블과 세션 로그인 결정 기록을 추가했다.

## [2026-06-05] maintenance | Separate human docs and AI wiki roles

- `docs/`는 사람이 보는 문서, `llm-wiki/`는 AI 작업 지식 레이어라는 역할 분리를 결정 기록으로 남겼다.
- FastAPI/WebSocket 가이드라인과 Python 코드 컨벤션의 AI 작업 기준을 `llm-wiki/wiki/`에 둔다고 정리했다.
- 한국어 주석/docstring 기준과 레이어별 테스트 기준을 AI 작업용 컨벤션에 반영했다.

## [2026-06-05] ingest | Backend framework and code conventions

- 사람용 backend/code convention 문서의 핵심을 AI 작업 기준으로 컴파일해 `backend-guidelines.md`, `code-conventions.md`, `backend-guidelines-summary.md`에 반영했다.
- FastAPI, WebSocket, 서버 간 client wrapper, 레이어 책임, 테스트 기준을 초기 작업 지식으로 정리했다.

## [2026-06-05] maintenance | LLM Wiki bootstrap

- `llm-wiki/index.md`를 콘텐츠 카탈로그로 만들고 `log.md`를 위키 작업 이력으로 분리했다.
- `current-status.md`, `project-map.md`, Karpathy LLM Wiki 개념, 초기 결정/출처 페이지를 추가했다.
- 위키를 읽거나 갱신할 때 `index.md`를 먼저 확인한다는 운영 기준을 세웠다.
