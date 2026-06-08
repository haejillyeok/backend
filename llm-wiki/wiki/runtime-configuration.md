---
title: Runtime Configuration
type: guide
updated: 2026-06-08
audience: ai
---

# Runtime Configuration

서버 프로세스가 직접 읽는 런타임 값은 `.env`와 OS 환경변수로 제어한다. OS 환경변수가
`.env`보다 우선하며, 값이 없으면 로컬 기본값을 쓴다. Docker Compose 인프라 host port는
서버 `.env` 관리 대상에 넣지 않는다.

## App Servers

`app/shared/core/config/http.py`와 `app/shared/core/config/grpc.py`는 앱 이름에서 서비스 prefix를
만든 뒤 서버 포트 값을 읽는다. HTTP host는 `127.0.0.1`, gRPC host는 `localhost`로 고정한다.

| Server | HTTP default | gRPC default |
| --- | --- | --- |
| `haejillyeok-be` | `127.0.0.1:8000` | `localhost:50051` |
| `haejillyeok-agent` | `127.0.0.1:8001` | `localhost:50052` |

`mise run dev-be`와 `mise run dev-agent`는 HTTP port 값을 uvicorn에 넘긴다. FastAPI
lifespan에서 함께 시작되는 gRPC 서버는 `GrpcSettings.from_app_name(...)` 값을 사용한다.

## Observability

서버의 APM exporter 연결은 `.env`의 활성화 값으로 제어한다. 기본값은 활성화다.
특정 상황에서 관측 전송을 끄고 싶을 때만 값을 비활성화한다. Collector가 기본 포트가 아닌
곳에 있으면 exporter endpoint 값을 실제 Collector endpoint로 맞춘다.
