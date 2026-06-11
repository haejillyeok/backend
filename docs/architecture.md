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
- `app/agent/repository`: Qdrant 단어 collection 접근 계층
- `app/agent/schemas`: 에이전트 요청, 응답, 단어 후보 모델
- `app/agent/services`: 에이전트 비즈니스 로직
- `app/agent/services/game_handlers`: game_type별 조건 검증과 Qdrant filter 전략
- `app/agent/utils`: 한국어 단어 분리와 결정적 hash 유틸리티
- `app/shared`: 두 서버가 공유하는 설정, 로깅, client helper
- `app/main.py`: 기존 실행 경로 호환을 위한 백엔드 앱 alias

DB 설정과 SQLAlchemy async engine 생명주기는 `app/shared/core/config/database.py`에 두고,
`be` 서버에서만 lifespan으로 적용합니다. `app/be/dependencies/database.py`는 요청 단위
세션을 제공합니다. `agent`는 Backend RDB에 접근하지 않으며, 자체 Qdrant repository와
Agent API schema만 소유합니다.

Agent 답변 생성은 Qdrant payload filter 검색을 우선합니다. `shiritori`, `chosung`,
`contains` handler가 검색 조건을 만들고, 후보 선택 서비스는 `used_words`를 제외한 후보 중
최대 10개를 무작위로 추린 뒤 하나를 반환합니다. 끝말잇기 후보가 없고 `USE_VLLM=true`이면
vLLM이 마지막 글자로 시작하는 2~4글자 단어를 한 번 생성합니다. Agent는 시작 글자, 길이,
완성형 한글 여부, `used_words` 중복 여부를 검증하며 실패하면 `no_candidate`를 반환합니다.
생성 단어의 사전 등재 여부는 별도 외부 사전 없이 완전히 검증할 수 없습니다.

운영 k3s 구성은 `deploy/k3s/`에 둡니다. Agent는 `NodePort 31080`, Qdrant는 local PV를 사용하는
StatefulSet, vLLM은 모델 hostPath가 있는 GPU worker 전용 Deployment입니다. 회사 k3s cluster를
공개 Ingress로 직접 노출하지 않고, 현재 외부 연결은 회사 control-plane에서 Azure VM
`127.0.0.1:31080`으로 연결한 SSH reverse tunnel과 Azure Nginx가 담당합니다.

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

사용자-facing 실시간 통신은 BE 서버의 `/ws/realtime` WebSocket 엔드포인트에서 처리합니다.
운영 HTTPS/TLS 앞단에서는 같은 path를 `wss://<host>/ws/realtime`로 노출합니다.
현재 realtime 채널은 JSON envelope 기반 `ping` / `realtime.pong` 연결 확인 메시지를 지원합니다.
