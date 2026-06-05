---
title: Common Protocol Response And Exceptions
type: decision
updated: 2026-06-05
audience: ai
---

# Common Protocol Response And Exceptions

## Decision

프로토콜 경계에서 쓰는 공통 response envelope와 커스텀 예외는 `app/shared/core`에서 관리한다.
성공 응답은 `success=true`, `data`, `error=null` 형태이고, 실패 응답은 `success=false`, `data=null`, `error` 형태다.
커스텀 예외는 `AppException`을 기준으로 관리하고, HTTP/gRPC handler가 각 프로토콜 응답으로 변환한다.

## Success Shape

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

## Error Shape

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "사람이 읽을 수 있는 메시지",
    "details": null
  }
}
```

## Implementation Rules

- 공통 response schema와 helper는 `app/shared/core/responses.py`에 둔다.
- 커스텀 애플리케이션 예외는 `app/shared/core/exceptions.py`의 `AppException`을 상속하거나 사용한다.
- `AppException`은 공통 `code`, `message`, `details`와 protocol adapter용 `http_status_code`, `grpc_status_code`를 가진다.
- BE REST exception handler 등록은 `app/be/api/exception_handlers.py`에서 관리한다.
- BE `create_app()`은 앱 생성 시 exception handler를 등록한다.
- HTTP endpoint는 성공 시 shared `ok(data)`를 반환한다.
- 서비스/도메인 계층은 실패 상황에서 `AppException` 계열 예외를 던질 수 있다.
- endpoint나 gRPC handler마다 같은 error response 조립 코드를 반복하지 않는다.

## Scope

- shared response/exception 타입은 HTTP와 gRPC 같은 프로토콜 경계에서 공통으로 사용할 수 있다.
- 현재 HTTP JSON 적용 범위는 BE `/api/v1/*` REST API다.
- root `/health`는 load balancer, container probe 같은 운영 확인용이므로 raw `{"status": "ok"}`를 유지한다.
- gRPC proto에 envelope 필드를 추가할지는 각 RPC 계약을 만들 때 결정하되, 예외 상태는 `AppException.grpc_status_code`를 기준으로 변환한다.
- Agent REST API에는 아직 적용하지 않았다. Agent에도 외부 API가 생기면 같은 shared 타입을 HTTP adapter에 연결한다.

## Current Error Codes

- `INVALID_CREDENTIALS`: 기존 닉네임의 비밀번호가 일치하지 않는 인증 실패
- `VALIDATION_ERROR`: FastAPI/Pydantic request validation 실패
- `HTTP_ERROR`: FastAPI `HTTPException` fallback
