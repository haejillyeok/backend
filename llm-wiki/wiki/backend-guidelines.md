---
title: Backend Guidelines
type: guide
updated: 2026-06-05
audience: ai
---

# Backend Guidelines

이 문서는 AI가 backend 코드를 작성하거나 수정할 때 우선 확인해야 하는 작업 기준이다. `docs/`는 사람 전용 문서이고, 이 파일이 AI 작업용 기준이다.

## Principles

- `be`와 `agent`는 같은 저장소에 있지만 독립 서버로 생각한다.
- 외부 HTTP API는 FastAPI router로 노출한다.
- 서버 간 내부 통신은 gRPC 계약과 client wrapper를 통해 호출한다.
- 사용자-facing 실시간 통신은 FastAPI WebSocket을 기본 선택지로 둔다.
- 코드, 설정, proto, 테스트가 최종 사실 기준이다.
- AI가 작업에 사용할 수 있는 기준과 결정은 `llm-wiki/`에 유지한다.

## FastAPI

### App Factory and Lifespan

- 각 서버는 `create_app()`에서 `FastAPI` 앱을 만든다.
- DB engine, gRPC server, background resource 같은 프로세스 생명주기 리소스는 `lifespan`에서 시작하고 종료한다.
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
- public API response에 내부 ORM model이나 proto message를 그대로 노출하지 않는다.

### OpenAPI and Swagger

- FastAPI 기본 OpenAPI schema와 Swagger UI를 사용한다.
- public HTTP endpoint는 `response_model`, `status_code`, `summary`, `operation_id`를 명시한다.
- 주요 실패 응답은 `responses`에 status code와 description을 남긴다.
- OpenAPI Generator나 프론트 client 생성에 대비해 `operation_id`는 안정적인 snake_case 이름으로 고정한다.
- 자세한 기준은 [openapi-swagger.md](openapi-swagger.md)를 따른다.

## gRPC

### Contract Ownership

- 서버가 제공하는 gRPC 계약은 호출 대상 서버가 소유한다.
- `be` 계약은 `app/be/grpc/proto/` 또는 공통 계약이면 `proto/`에 둔다.
- `agent` 계약은 `app/agent/grpc/proto/` 또는 공통 계약이면 `proto/`에 둔다.
- 한 서버가 다른 서버의 service/repository를 직접 import하지 않는다.

### Client Pattern

- gRPC channel 생성은 `app/shared/grpc/clients.py`의 helper를 사용한다.
- 기능별 client wrapper는 `app/shared/clients/{feature}.py`에 둔다.
- endpoint나 service에서 generated stub을 직접 흩뿌리지 않는다.
- 모든 outbound RPC에는 timeout/deadline을 명시한다.

### Deadlines and Cancellation

- client는 현실적인 deadline을 설정한다. 무기한 대기는 금지한다.
- server handler는 긴 작업 중 취소 여부를 확인하고 불필요한 처리를 중단할 수 있게 설계한다.
- server가 또 다른 gRPC를 호출하는 경우, 기존 요청의 timeout budget을 넘기지 않는다.

### Status Codes

- 잘못된 인자는 `INVALID_ARGUMENT`를 사용한다.
- 없는 리소스는 `NOT_FOUND`를 사용한다.
- 현재 상태 때문에 처리할 수 없으면 `FAILED_PRECONDITION` 또는 `ABORTED`를 구분해서 사용한다.
- deadline 초과는 `DEADLINE_EXCEEDED`, 호출자 취소는 `CANCELLED`로 다룬다.
- 내부 예외를 무조건 `UNKNOWN`으로 숨기지 말고 가능한 한 의도된 status로 변환한다.

### Health and Lifecycle

- 각 gRPC 서버는 health check 계약을 제공한다.
- FastAPI lifespan에서 gRPC server를 시작하고 graceful shutdown으로 종료한다.
- 종료 시 새 요청을 받지 않도록 하고 진행 중인 요청에 짧은 grace period를 둔다.

### Proto Rules

- proto package는 서버와 도메인을 드러내는 이름을 쓴다.
- message 필드는 제거하거나 재사용하지 않는다. 삭제가 필요하면 field number를 reserved 처리한다.
- 새 필드는 backward compatible하게 optional/default-safe하게 추가한다.
- generated Python 파일은 직접 수정하지 않는다.

## WebSocket

### Use Cases

WebSocket은 사용자-facing 양방향 통신이 필요한 경우에 사용한다.

- 진행 상태 push
- 알림
- 채팅 또는 에이전트 실행 스트림
- 서버 이벤트를 즉시 전달해야 하는 화면

단순 서버 간 호출은 WebSocket이 아니라 gRPC를 우선한다. 단방향 이벤트가 충분하면 HTTP polling이나 server-sent events도 검토한다.

### Route Placement

- WebSocket endpoint는 `app/{server}/api/endpoints/{feature}_ws.py` 또는 `realtime.py`에 둔다.
- URL은 `/ws/{feature}` 또는 `/api/v1/ws/{feature}` 중 하나로 통일한다.
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
