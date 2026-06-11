# Backend Guidelines

이 문서는 사람이 읽을 수 있도록 FastAPI, WebSocket 사용 기준을 정리한 문서입니다. AI 작업용 기준은 `llm-wiki/`에도 함께 유지합니다.

## Principles

- `be`와 `agent`는 같은 저장소에 있지만 독립 서버로 생각한다.
- 외부 HTTP API는 FastAPI router로 노출한다.
- 서버 간 내부 통신이 필요하면 HTTP API와 client wrapper를 통해 호출한다.
- 사용자-facing 실시간 통신은 FastAPI WebSocket을 기본 선택지로 둔다.
- `docs/`는 사람 전용 문서이고, AI가 작업할 때 쓰는 기준은 `llm-wiki/`에 둔다.

## FastAPI

### App Factory and Lifespan

- 각 서버는 `create_app()`에서 `FastAPI` 앱을 만든다.
- DB engine, background resource 같은 프로세스 생명주기 리소스는 `lifespan`에서 시작하고 종료한다.
- `startup`/`shutdown` 이벤트보다 `lifespan` context manager를 우선한다.
- 테스트에서는 `create_app()`을 호출해서 앱을 만들고 dependency override를 주입할 수 있게 유지한다.

### Router Structure

- public router는 `app/{server}/api/router.py`에서 `APIRouter(prefix="/api/v1")`로 묶는다.
- endpoint 파일은 `app/{server}/api/endpoints/{feature}.py`에 둔다.
- endpoint 파일은 request parsing, dependency wiring, response mapping만 담당한다.
- 비즈니스 로직은 `services/`, DB 접근은 `repository/`, 입출력 모델은 `schemas/`에 둔다.
- router-level 공통 인증, 태그, response metadata가 필요하면 `APIRouter(...)` 또는 `include_router(...)`에 둔다.

### Dependencies

- FastAPI dependency는 요청 단위 리소스와 권한 확인에 사용한다.
- DB session처럼 cleanup이 필요한 dependency는 `async with` 또는 `yield` dependency로 관리한다.
- service 객체를 만들 때 endpoint 안에서 직접 생성하지 말고 `dependencies/services.py`를 통해 주입한다.
- dependency가 많아지면 endpoint 함수 본문보다 dependency provider의 책임을 먼저 정리한다.

### Error Handling

- request validation은 Pydantic/FastAPI validation에 맡긴다.
- 도메인 오류는 service 계층에서 명시적인 예외로 표현하고 endpoint에서 HTTP status로 변환한다.
- endpoint에서 broad `Exception`을 잡아 삼키지 않는다.
- 클라이언트가 고칠 수 있는 입력 문제는 `400` 또는 `422`, 인증/권한 문제는 `401`/`403`, 리소스 부재는 `404`, 충돌은 `409`를 우선 검토한다.

### Response Models

- response schema는 `app/{server}/schemas/response/`에 둔다.
- endpoint는 dict를 직접 누적하기보다 response model을 통해 반환 shape를 고정한다.
- public API response에 내부 ORM model을 그대로 노출하지 않는다.

## Server-to-Server Communication

- 한 서버가 다른 서버의 service/repository를 직접 import하지 않는다.
- 서버 간 호출은 대상 서버의 HTTP API 계약을 통해 수행한다.
- 기능별 client wrapper는 `app/shared/clients/{feature}.py`에 둔다.
- endpoint나 service에서 HTTP client 호출 세부를 흩뿌리지 않는다.
- 모든 outbound HTTP 호출에는 timeout을 명시한다.
- retry가 필요하면 멱등성, timeout budget, 실패 로그 기준을 함께 정한다.


## WebSocket

### Use Cases

WebSocket은 다음처럼 사용자-facing 양방향 통신이 필요한 경우에 사용한다.

- 진행 상태 push
- 알림
- 채팅 또는 에이전트 실행 스트림
- 서버 이벤트를 즉시 전달해야 하는 화면

단순 서버 간 호출은 WebSocket이 아니라 HTTP API 호출을 우선한다. 단방향 이벤트가 충분하면 HTTP polling이나 server-sent events도 검토한다.

### Route Placement

- WebSocket endpoint는 `app/{server}/api/endpoints/{feature}_ws.py` 또는 `realtime.py`에 둔다.
- URL은 `/ws/{feature}` 형식으로 통일하고, REST API router와 분리한다.
- 인증/권한 정책은 HTTP API와 같은 원칙을 적용한다.

### Connection Management

- 연결 수락 전 인증 정보를 검증한다.
- connection manager는 active connection, user/session mapping, cleanup을 책임진다.
- disconnect 시 반드시 connection registry에서 제거한다.
- 메시지는 JSON envelope로 감싼다.

```json
{
  "type": "agent.progress",
  "request_id": "uuid",
  "payload": {}
}
```

### Reliability

- 클라이언트 재연결을 전제로 설계한다.
- 메시지 순서가 중요하면 `sequence`나 `created_at`을 포함한다.
- 중복 수신이 문제가 되면 `event_id`를 포함하고 멱등 처리한다.
- 큰 payload는 WebSocket으로 직접 보내지 말고 저장소/API 참조를 보낸다.
- heartbeat 또는 ping/pong 정책을 정하고 idle connection을 정리한다.

### Testing

- WebSocket endpoint는 connect, message send/receive, disconnect cleanup을 테스트한다.
- 인증 실패와 비정상 종료 케이스를 포함한다.
- connection manager는 가능한 한 FastAPI endpoint와 분리해서 단위 테스트한다.

## References

- FastAPI Bigger Applications: <https://fastapi.tiangolo.com/tutorial/bigger-applications/>
- FastAPI Dependencies: <https://fastapi.tiangolo.com/tutorial/dependencies/>
- FastAPI Lifespan Events: <https://fastapi.tiangolo.com/advanced/events/>
- FastAPI WebSockets: <https://fastapi.tiangolo.com/advanced/websockets/>
- FastAPI Testing WebSockets: <https://fastapi.tiangolo.com/advanced/testing-websockets/>
