# API

## Common Response

프로토콜 경계에서 사용하는 공통 응답 envelope입니다. HTTP API는 이 형태를 JSON으로 반환하고,
gRPC handler는 같은 구조를 proto 응답 필드나 metadata로 매핑할 수 있습니다.
BE `/api/v1/*` REST API는 이 envelope를 사용합니다. 운영 probe 성격의 root `/health`는 예외적으로 raw 응답을 유지합니다.

Success:

```json
{
  "success": true,
  "data": {}
}
```

Error:

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

커스텀 예외는 shared `AppException` 계열로 관리합니다. 예외는 공통 `code`, `message`, `details`와 함께
HTTP status, gRPC status metadata를 가질 수 있고, 각 프로토콜 handler가 자기 응답 형식으로 변환합니다.
공개 에러 코드는 shared `ErrorCode` enum과 `ErrorDefinition` catalog에서 관리합니다.
각 error definition은 error type, 기본 message, HTTP status, gRPC status, WebSocket close code를 함께 가집니다.
Swagger 실패 응답은 `ErrorResponse` schema를 참조하고, endpoint별 예시에 실제 `code` 값을 함께 표시합니다.
같은 HTTP status에서 여러 application error code가 나올 수 있으면 Swagger `examples`로 각각의 code 예시를 모두 표시합니다.

### Error Codes

| Code | Type | HTTP | gRPC | WebSocket | Meaning |
| --- | --- | --- | --- | --- | --- |
| `INVALID_CREDENTIALS` | `AUTHENTICATION` | `401` | `UNAUTHENTICATED` | `1008` | 기존 닉네임의 비밀번호가 일치하지 않음 |
| `SESSION_EXPIRED` | `AUTHENTICATION` | `401` | `UNAUTHENTICATED` | `1008` | 세션 만료 |
| `VALIDATION_ERROR` | `VALIDATION` | `422` | `INVALID_ARGUMENT` | `1008` | 요청 body validation 실패 |
| `HTTP_ERROR` | `INTERNAL` | `500` | `UNKNOWN` | `1011` | FastAPI `HTTPException` fallback |

## BE Health

서비스 상태 확인용 엔드포인트입니다.

| Method | Path | Response |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/api/v1/health` | `{"success": true, "data": {"status": "ok"}}` |

## BE Auth

닉네임과 비밀번호로 가입 겸 로그인을 처리합니다. 닉네임이 없으면 새 유저를 만들고,
이미 있으면 비밀번호를 검증합니다.

### POST `/api/v1/auth/login`

Request:

```json
{
  "nickname": "초보자",
  "password": "secret-password"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "user": {
      "public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7f",
      "nickname": "초보자"
    },
    "is_new_user": true,
    "expires_at": "2026-06-12T00:00:00Z"
  }
}
```

성공하면 `session_token` 쿠키를 설정합니다. 쿠키는 `HttpOnly`, `SameSite=Lax`로 발급하고,
`prod` 환경에서는 `Secure`를 함께 사용합니다.

| Status | Meaning |
| --- | --- |
| `200` | 가입 또는 로그인 성공 |
| `401` / `INVALID_CREDENTIALS` | 기존 닉네임의 비밀번호가 일치하지 않음 |
| `422` / `VALIDATION_ERROR` | 요청 body validation 실패 |

## Agent Health

에이전트 상태 확인용 엔드포인트입니다.

| Method | Path | Response |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/api/v1/health` | `{"status": "ok"}` |

## Internal gRPC Health

서버 간 통신용 내부 gRPC 헬스 체크 계약입니다.

| Server | Service | RPC | Request | Response |
| --- | --- | --- | --- | --- |
| `be` | `haejillyeok.be.internal.v1.InternalHealth` | `Ping` | `PingRequest(caller)` | `PingResponse(service, status)` |
| `agent` | `haejillyeok.agent.internal.v1.InternalHealth` | `Ping` | `PingRequest(caller)` | `PingResponse(service, status)` |
