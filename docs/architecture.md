# Architecture

현재 프로젝트는 하나의 저장소에서 백엔드 서버와 에이전트 서버를 함께 관리합니다.

- `app/be/main.py`: 백엔드 FastAPI 앱 생성
- `app/be/api`: 백엔드 API 라우터와 엔드포인트
- `app/be/dependencies`: 백엔드 FastAPI dependency provider
- `app/be/repository`: 백엔드 데이터 접근 계층
- `app/be/schemas`: 백엔드 요청/응답 모델
- `app/be/services`: 백엔드 비즈니스 로직과 WebSocket connection manager
- `app/agent/main.py`: 에이전트 FastAPI 앱 생성
- `app/agent/api`: 에이전트 API 라우터와 엔드포인트
- `app/agent/dependencies`: 에이전트 FastAPI dependency provider
- `app/agent/services`: 에이전트 비즈니스 로직
- `app/shared`: 두 서버가 공유하는 설정, 로깅, client helper
- `app/main.py`: 기존 실행 경로 호환을 위한 백엔드 앱 alias

DB 설정과 SQLAlchemy async engine 생명주기는 `app/shared/core/config/database.py`에 두고,
`be` 서버에서만 lifespan으로 적용합니다. `app/be/dependencies/database.py`는 요청 단위
세션을 제공합니다. `agent`는 DB 적용 코드, repository, schema를 갖지 않고, 필요한 데이터는
백엔드 API 또는 서버 간 client를 통해 요청합니다.

요청 감사 로그는 `app/shared/core/audit.py`의 공통 이벤트 포맷을 사용합니다.
REST 요청은 `app/shared/core/http_audit.py`의 FastAPI middleware가 시작/완료/실패 이벤트를 기록합니다.
로그에는 method/path, status, duration, peer 같은 메타데이터만 남기고
request/response body와 비밀번호 같은 민감 payload는 남기지 않습니다.

실행 환경은 `local`, `dev`, `prod`만 허용합니다. DB 접속 정보는 프로젝트 루트의
`.env`에서 따로 관리하고, URL은 코드에서 조립합니다.
pool 크기와 timeout 같은 값은 코드에서 관리합니다.

서버 간 통신이 필요할 때는 한 서버가 다른 서버의 내부 service를 직접 import하지 않고,
호출 대상 서버가 소유한 HTTP API 계약과 `app/shared/clients`의 기능별 client wrapper를 통해
호출합니다.

사용자-facing 실시간 통신은 BE 서버의 `/api/v1/ws/realtime` WebSocket 엔드포인트에서 처리합니다.
운영 HTTPS/TLS 앞단에서는 같은 path를 `wss://<host>/api/v1/ws/realtime`로 노출합니다.
현재 realtime 채널은 JSON envelope 기반 `ping` / `realtime.pong` 연결 확인 메시지를 지원합니다.
