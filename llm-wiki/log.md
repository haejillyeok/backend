# LLM Wiki Log

이 파일은 `llm-wiki/` 정보 자체의 시간순 변경 이력입니다. 새 항목은 위에 추가합니다.
코드 변경 상세는 Git history, PR, issue에서 확인하고, 이 파일에는 위키 페이지의 지식, 계약, 정책,
컨벤션이 어떻게 바뀌었는지만 남깁니다.

## [2026-06-13] maintenance | Align timestamps on KST

- `runtime-configuration.md`의 DB timestamp 기준을 UTC가 아니라 KST timezone-aware datetime으로 정정했다.
- 서버가 생성해 public API와 WebSocket payload로 내보내는 timestamp도 KST offset을 포함한다는 기준을 정리했다.

## [2026-06-13] maintenance | Add lobby room snapshot contract

- `realtime-websocket.md`와 `sunset-game-domain.md`에 `/ws/lobby/rooms/{room_public_id}` 연결 성공 직후 `lobby.room.snapshot`으로 현재 활성 멤버 목록을 초기화한다는 계약을 추가했다.
- Snapshot 이후 멤버 변경은 `lobby.room.joined`, `lobby.room.left` event로 반영한다는 클라이언트 상태 관리 기준을 정리했다.

## [2026-06-13] maintenance | Complete lobby leave contract

- `realtime-websocket.md`와 `sunset-game-domain.md`에 로비 목록의 현재 유저 active membership 응답, REST room leave, 방장 승계, 마지막 멤버 퇴장 시 room 폐쇄 기준을 반영했다.
- `lobby.room.left` event가 REST 퇴장과 WebSocket grace leave 모두에서 같은 퇴장 결과 payload를 전달한다는 기준을 정리했다.

## [2026-06-13] maintenance | Clarify Postman WebSocket collection format

- `openapi-swagger.md`에 Postman file import의 collection v2.1 JSON은 `ws://` URL도 HTTP
  request로 import하고, 내부 `ws-raw-request` JSON은 일반 import 포맷으로 인식되지 않는다는
  기준을 추가했다.
- 이 스크립트는 WebSocket 전용 Postman collection JSON을 생성하지 않고, WebSocket 요청은
  Postman UI에서 직접 만들며 `sessionToken` environment 변수를 `Cookie` header로 재사용한다는
  기준을 정리했다.
- 로컬과 운영 WebSocket URL을 같은 변수로 전환할 수 있도록 WebSocket base URL은 host/port로 쪼개지
  않고 `baseWs` 하나로 관리한다는 기준을 반영했다.

## [2026-06-13] maintenance | Clarify game session public ID naming

- `sunset-game-domain.md`와 API 문서 기준에서 게임 한 판의 공개 식별자는 `session_public_id`가 아니라 `game_session_public_id`로 부른다는 명명 기준을 반영했다.
- `game_session_public_id`는 라운드 ID가 아니며, 라운드/턴은 같은 game session 안의 phase 또는 round number로 관리한다는 구분을 명확히 했다.

## [2026-06-13] maintenance | Separate match resume token from login session

- `sunset-game-domain.md`에 `game_session_public_id`는 게임 세션 공개 식별자이고, `game_session_token`은 현재 실제 유저 참가자에게만 발급되는 match 복구 credential이라는 기준을 추가했다.
- `sunset-game-database-design.md`에 `game.session_participants.resume_token_hash`, `resume_token_expires_at` 컬럼과 partial index 기준을 추가했다.
- 로그인 `session_token` 만료는 진행 중 match를 즉시 끊지 않고, `/ws/match` 재연결은 `game_session_token`으로 participant identity를 복원할 수 있다는 기준을 남겼다.

## [2026-06-13] maintenance | Add BE Postman generation policy

- `openapi-swagger.md`에 Postman import용 JSON은 BE OpenAPI schema와 명시 WebSocket 정의에서 생성하고, HTTP API collection과 WebSocket collection을 별도 파일로 관리하며, Agent 서버와 BE `/api/v1/agent/*` proxy endpoint는 제외한다는 기준을 추가했다.
- Postman environment에서 `baseUrl`, `baseWs`, 인증/session, room/session 예시 변수를 관리하고, 로그인/회원가입 응답의 `session_token` 쿠키를 `sessionToken` 변수에 저장한다는 기준을 남겼다.

## [2026-06-12] maintenance | Add game API enum contract

- `sunset-game-domain.md`와 `openapi-swagger.md`에 `game_type`, room/session `status`, `participant_type` 같은 공개 API의 닫힌 문자열 값은 enum으로 관리하고 Swagger에 enum 목록을 노출한다는 기준을 추가했다.

## [2026-06-12] maintenance | Split signup and login auth contract

- `backend-guidelines.md`와 `2026-06-05-auth-session-login.md`에 `POST /api/v1/auth/signup`은 신규 계정 생성, `POST /api/v1/auth/login`은 기존 계정 인증만 담당한다는 기준을 반영했다.
- 로그인 request는 `account_id`, `password`만 받고, 회원가입 중복 계정/닉네임은 `409 AUTH_USER_CONFLICT`로 처리한다는 계약을 남겼다.

## [2026-06-12] maintenance | Clarify Grafana dashboard link policy

- `observability-stack.md`에 Grafana dashboard 간 이동은 `type: link`와 `/d/<dashboard_uid>` URL을 사용하고, `type: dashboards`는 tag 기반 목록 확장용이라 빈 tag와 함께 쓰지 않는다는 기준을 추가했다.

## [2026-06-12] maintenance | Add generic WebSocket APM observability

- `observability-stack.md`에 WebSocket 연결, 메시지, 오류, 종료, 연결 지속 시간 metric과 낮은 cardinality label 기준을 추가했다.
- Grafana trace dashboard는 Auth 도메인 고정 패널이 아니라 service/repository layer 기준으로 조회하고, WebSocket APM dashboard는 별도 범용 dashboard로 관리한다는 기준을 남겼다.

## [2026-06-12] maintenance | Add room lobby heartbeat and grace leave policy

- `realtime-websocket.md`에 room 로비 WebSocket은 client `ping`을 heartbeat로 보고, 45초 timeout 후 연결을 닫으며, 90초 grace time 안에 재연결하지 않으면 DB 퇴장 처리한다는 기준을 추가했다.
- `sunset-game-domain.md`에 grace 퇴장 확정 시 `game.room_members.left_at`을 기록하고 같은 room 연결에 `lobby.room.left`를 broadcast한다는 기준을 남겼다.

## [2026-06-12] maintenance | Add REST room APIs and path-based lobby WebSocket

- `realtime-websocket.md`에 객실 목록 조회, 객실 생성, 객실 참여는 REST API가 담당하고 `/ws/lobby/rooms/{room_public_id}`는 활성 room member만 연결하는 path 기반 room 로비 WebSocket이라는 기준을 반영했다.
- `sunset-game-domain.md`에 room 생성 시 방장을 첫 room member로 등록하고, join 성공 후 같은 room WebSocket 연결에 `lobby.room.joined`를 broadcast한다는 현재 계약을 정리했다.

## [2026-06-12] maintenance | Restructure websocket docs format

- `realtime-websocket.md`에 `/ws-docs`는 한국어 사용자가 읽는 endpoint matrix, 공통 envelope, message direction, endpoint별 contract, error/close code 중심의 WebSocket reference 형식으로 관리한다는 기준을 추가했다.
- WebSocket message heading은 `요청(Request)`, `응답(Response)`, `이벤트(Event)`처럼 한국어를 우선하고, 목차는 큰 섹션만 보여주며, 유저 플로우는 작은 Mermaid sequence diagram 여러 개로 나누어 관리한다는 기준을 남겼다.

## [2026-06-12] maintenance | Add lobby websocket and room join contract

- `realtime-websocket.md`에 `/ws/lobby`의 세션 쿠키 인증, room 구독 메시지, `lobby.room.joined` broadcast 기준을 추가했다.
- `sunset-game-domain.md`에 room 참여는 REST API가 DB `game.room_members`에 저장하고, lobby WebSocket은 연결과 구독 상태만 process memory에 보관한다는 기준을 추가했다.

## [2026-06-12] maintenance | Add test coverage threshold

- `code-conventions.md`에 `pytest`가 전체 `app` package coverage를 측정하고 총 coverage 90% 이상을 유지한다는 테스트 기준을 추가했다.

## [2026-06-12] maintenance | Add BE protected router session policy

- `backend-guidelines.md`에 BE REST API는 public router와 protected router를 분리하고, protected router에서 `session_token` 기반 `get_current_user` dependency를 공통 적용한다는 기준을 추가했다.
- 로그인과 health 계열 API만 public router에 두고, 새 BE API는 기본적으로 protected router에 등록한다는 운영 기준을 남겼다.

## [2026-06-12] maintenance | Add WebSocket docs TOC and Mermaid flow

- `realtime-websocket.md`에 `/ws-docs` 렌더러가 heading 기반 자동 목차와 Mermaid code block 렌더링을 지원한다는 문서 운영 기준을 추가했다.
- `ws-api.md`에는 게임 시작 REST gate, lobby broadcast, match 연결 권한 확인 흐름을 Mermaid sequence diagram으로 유지한다는 기준을 남겼다.

## [2026-06-11] maintenance | Add game session REST gate contract

- `sunset-game-domain.md`에 게임 진행 WebSocket 전 단계로 REST 기반 게임 시작과 세션 진입 권한 확인 기준을 추가했다.
- 로그인 `session_token`으로 현재 유저를 확인하고, 게임 시작 시 고정된 `session_participants`만 세션 진입을 허용하는 기준을 남겼다.
- `/ws/realtime`은 계속 연결 테스트용이며 이후 `/ws/lobby`, `/ws/match`가 같은 참가자 권한 기준을 재사용해야 한다고 정리했다.
- REST handler에서 lobby WebSocket 알림이 필요하면 connection manager 또는 서버 간 event bus로 이미 열린 연결에 broadcast하고, match 연결 후에는 `game_session_id + participant_id + user_id` identity를 기준으로 진행한다는 기준을 추가했다.
- start API는 room row lock으로 같은 room의 동시 요청을 직렬화하고, active session이 이미 있으면 기존 `game_session_public_id`를 반환하는 멱등 기준을 추가했다.

## [2026-06-11] maintenance | Add Sunset game DB design draft

- `sunset-game-database-design.md`에 해질녘 게임 플랫폼의 결과/복구 중심 DB 저장 범위와 table 초안을 정리했다.
- UUID v7은 row 식별자와 외부 노출 식별자에 쓰고, 게임 안 순서/번호/점수/개수는 integer로 둔다는 기준을 추가했다.
- `session_phases`, `participant_actions`, `state_snapshots`, `game_events`를 공통 진행 기록으로 두고 단어 게임은 `word_game` 확장 table로 분리하는 기준과 Mermaid ERD를 추가했다.

## [2026-06-11] maintenance | Split lobby and match WebSocket direction

- `realtime-websocket.md`에서 `/ws/realtime`을 실제 게임 상태가 아닌 ping/pong 연결 테스트용 endpoint로 정리했다.
- `sunset-game-domain.md`와 결정 기록에 실제 게임 통신은 `/ws/lobby`, `/ws/match`로 처음부터 분리한다는 기준을 반영했다.
- 기획 점검 결과 투표 시점을 라운드 종료가 아니라 게임/모든 라운드 종료 이후로 정리하고, AI 우승/보상, 점수 구간, 라운드 단위는 열린 질문으로 남겼다.

## [2026-06-11] ingest | Add Kkutu reference takeaways

- `sunset-game-domain.md`에 Kkutu 분석에서 참고할 빠른 시작 상태 머신, lobby/match WebSocket 관심사 분리, command-response와 broadcast 분리 기준을 반영했다.
- 로비/객실/매치 snapshot, 재접속 복구, 경기 화면 상태 분리, 게스트 플레이 여부를 향후 결정 지점으로 정리했다.

## [2026-06-11] ingest | Add Sunset game domain model

- `sunset-game-domain.md`에 해질녘 게임의 로비, 객실, 게임 세션, 라운드, 턴, 점수, 투표 도메인 기준을 정리했다.
- WebSocket은 BE가 권위 있는 게임 상태를 유지하고 snapshot/event로 클라이언트를 동기화하는 방향으로 정리했다.
- Agent는 AI 손님의 단어 후보만 제공하고 게임 상태, 점수, 투표 계산은 Backend가 소유한다는 경계를 명시했다.

## [2026-06-11] maintenance | Add BE to Agent health runtime contract

- `runtime-configuration.md`에 BE가 Agent health API를 호출할 때 전용 client wrapper와 배포 주입 설정을 사용한다는 기준을 추가했다.
- Agent 연결 정보는 기본값 없이 GitHub Secrets에서 필수로 주입한다는 배포 기준을 정리했다.

## [2026-06-11] implementation | Integrate Qdrant Agent MVP

- 별도 Agent 작업공간의 끝말잇기 MVP를 monorepo `app/agent` 소유 구조로 이식했다.
- Qdrant repository, game handler, 후보 선택, 멱등성, 비동기 적재와 사용 횟수 갱신 계층을 추가했다.
- 프롬프트는 `.txt`가 아닌 `app/agent/prompts.py` 변수로 관리한다.
- 단일 Docker image에서 `APP_MODULE=agent`, `PORT=8001`로 실행하도록 k3s manifest를 추가했다.
- Qdrant local PV와 vLLM 단일 GPU replica, 모델 hostPath, `enableServiceLinks=false`를 배포 기준으로 고정했다.
- 회사 NodePort `31080`에서 Azure localhost로 이어지는 SSH reverse tunnel과 Azure Nginx를 외부 연결 경계로 기록했다.
- Agent API, 한국어 처리, Qdrant 중복 적재, k3s manifest 테스트를 추가했다.

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
