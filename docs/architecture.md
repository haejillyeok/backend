# Architecture

현재 프로젝트는 하나의 저장소에서 백엔드 서버와 에이전트 서버를 함께 관리합니다.

- `app/be/main.py`: 백엔드 FastAPI 앱 생성
- `app/be/api`: 백엔드 API 라우터와 엔드포인트
- `app/be/dependencies`: 백엔드 FastAPI dependency provider
- `app/be/repository`: 백엔드 데이터 접근 계층
- `app/be/schemas`: 백엔드 요청/응답 모델
- `app/be/services`: 백엔드 비즈니스 로직
- `app/agent/main.py`: 에이전트 FastAPI 앱 생성
- `app/agent/api`: 에이전트 API 라우터와 엔드포인트
- `app/agent/dependencies`: 에이전트 FastAPI dependency provider
- `app/agent/services`: 에이전트 비즈니스 로직
- `app/shared`: 두 서버가 공유하는 설정, 로깅, 통신 클라이언트
- `app/main.py`: 기존 실행 경로 호환을 위한 백엔드 앱 alias

DB 설정과 SQLAlchemy async engine 생명주기는 `app/shared/core/config/database.py`에 두고,
`be` 서버에서만 lifespan으로 적용합니다. `app/be/dependencies/database.py`는 요청 단위
세션을 제공합니다. `agent`는 DB 적용 코드, repository, schema를 갖지 않고, 필요한 데이터는
백엔드 API 또는 서버 간 client를 통해 요청합니다.

실행 환경은 `local`, `dev`, `prod`만 허용합니다. DB 접속 정보는 프로젝트 루트의
`.env`에서 따로 관리하고, URL은 코드에서 조립합니다.
pool 크기와 timeout 같은 값은 코드에서 관리합니다.

서버 간 통신이 필요할 때는 한 서버가 다른 서버의 내부 service를 직접 import하지 않고,
`app/shared/clients`의 HTTP client를 통해 API 계약으로 호출합니다.
