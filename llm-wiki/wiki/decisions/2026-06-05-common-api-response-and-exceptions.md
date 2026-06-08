---
title: Common Protocol Response And Exceptions
type: decision
updated: 2026-06-09
audience: ai
superseded_by: 2026-06-09-remove-application-grpc
---

# Common Protocol Response And Exceptions

## Decision

프로토콜 경계에서 쓰는 공통 response envelope와 커스텀 예외는 `app/shared/core`에서 관리한다.
성공 응답은 `success=true`, `data` 형태이고, 실패 응답은 `success=false`, `data=null`, `error` 형태다.
커스텀 예외는 `AppException`을 기준으로 관리하고, HTTP handler가 JSON 응답으로 변환한다.

> 2026-06-09 기준으로 애플리케이션 gRPC는 제거되었고, gRPC status 관련 내용은
> [Remove Application gRPC](2026-06-09-remove-application-grpc.md) 결정으로 대체되었다.

## Success Shape

```json
{
  "success": true,
  "data": {}
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
- 공개 error code는 `app/shared/core/error_codes.py`의 `ErrorCode`, `ErrorType`, `ErrorDefinition`, `ERROR_DEFINITIONS` catalog에서 관리한다.
- 각 `ErrorDefinition`은 기본 message, HTTP status, WebSocket close code를 함께 가진다.
- Swagger 문서용 성공 응답은 `SuccessResponse[T]`, 실패 응답은 `ErrorResponse`를 사용해 성공/실패 envelope를 명확히 구분한다.
- 커스텀 애플리케이션 예외는 `app/shared/core/exceptions.py`의 `AppException`을 상속하거나 사용한다.
- `AppException`은 `ErrorCode`를 받으면 catalog에서 `message`, `http_status_code`, `websocket_close_code`, `error_type` 기본값을 가져온다.
- WebSocket처럼 JSON error envelope를 직접 보내야 하는 경계는 `AppException.to_error_payload()`와 `websocket_close_code`를 함께 사용한다.
- BE REST exception handler 등록은 `app/be/api/exception_handlers.py`에서 관리한다.
- BE `create_app()`은 앱 생성 시 exception handler를 등록한다.
- HTTP endpoint는 성공 시 shared `ok(data)`를 반환한다.
- 서비스/도메인 계층은 실패 상황에서 `AppException` 계열 예외를 던질 수 있다.
- Swagger 실패 응답은 `app/shared/core/openapi.py`의 helper로 `ErrorResponse` schema와 endpoint별 example/examples를 함께 표시한다.
- endpoint는 가능한 한 `error_responses_by_status(codes=[...])`에 `ErrorCode` 목록을 넘겨 HTTP status별 Swagger responses를 자동 생성한다.
- 같은 HTTP status에 application error code가 여러 개면 helper가 Swagger `examples`에 모두 노출한다.
- 성공 응답에는 `error` 필드를 넣지 않는다.
- FastAPI가 OpenAPI 생성 중 example의 `None` 값을 제거하므로, BE 앱은 `install_openapi_schema(app)`로 `ErrorResponse` example의 `data: null`, `details: null`을 복원한다.
- endpoint마다 같은 error response 조립 코드를 반복하지 않는다.

## Scope

- shared response/exception 타입은 HTTP와 WebSocket 같은 프로토콜 경계에서 공통으로 사용할 수 있다.
- 현재 HTTP JSON 적용 범위는 BE `/api/v1/*` REST API다.
- root `/health`는 load balancer, container probe 같은 운영 확인용이므로 raw `{"status": "ok"}`를 유지한다.
- WebSocket error/close 처리는 `AppException.websocket_close_code`를 기준으로 설계한다.
- Agent REST API에는 아직 적용하지 않았다. Agent에도 외부 API가 생기면 같은 shared 타입을 HTTP adapter에 연결한다.

## Current Error Codes

- `INVALID_CREDENTIALS`: 기존 닉네임의 비밀번호가 일치하지 않는 인증 실패
- `SESSION_EXPIRED`: 세션 만료
- `VALIDATION_ERROR`: FastAPI/Pydantic request validation 실패
- `HTTP_ERROR`: FastAPI `HTTPException` fallback
