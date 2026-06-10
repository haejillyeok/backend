# API

## Common Response

HTTP API에서 사용하는 공통 응답 envelope입니다. HTTP API는 이 형태를 JSON으로 반환합니다.
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
HTTP status metadata를 가질 수 있고, HTTP handler가 JSON 응답 형식으로 변환합니다.
공개 에러 코드는 shared `ErrorCode` enum과 `ErrorDefinition` catalog에서 관리합니다.
각 error definition은 error type, 기본 message, HTTP status, WebSocket close code를 함께 가집니다.
Swagger 실패 응답은 `ErrorResponse` schema를 참조하고, endpoint별 예시에 실제 `code` 값을 함께 표시합니다.
같은 HTTP status에서 여러 application error code가 나올 수 있으면 Swagger `examples`로 각각의 code 예시를 모두 표시합니다.

### Error Codes

| Code | Type | HTTP | WebSocket | Meaning |
| --- | --- | --- | --- | --- |
| `INVALID_CREDENTIALS` | `AUTHENTICATION` | `401` | `1008` | 기존 계정 ID의 비밀번호가 일치하지 않음 |
| `SESSION_EXPIRED` | `AUTHENTICATION` | `401` | `1008` | 세션 만료 |
| `VALIDATION_ERROR` | `VALIDATION` | `422` | `1008` | 요청 body validation 실패 |
| `HTTP_ERROR` | `INTERNAL` | `500` | `1011` | FastAPI `HTTPException` fallback |

## BE Health

서비스 상태 확인용 엔드포인트입니다.

| Method | Path | Response |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/api/v1/health` | `{"success": true, "data": {"status": "ok"}}` |

## BE Auth

계정 ID와 비밀번호로 가입 겸 로그인을 처리합니다. 계정 ID가 없으면 새 유저를 만들고,
이미 있으면 비밀번호를 검증합니다. 새 유저 생성 시 닉네임은 타 유저와 중복될 수 없습니다.

- 계정 ID: 영어 문자, 숫자, `_`만 허용, 3~20자
- 비밀번호: 한글, 영어, 숫자, 특수자 입력 가능, 8~20자
- 닉네임: 한글, 영어, 숫자, `_`만 허용, 3~20자

### POST `/api/v1/auth/login`

Request:

```json
{
  "account_id": "player_001",
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
      "account_id": "player_001",
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
| `401` / `INVALID_CREDENTIALS` | 기존 계정 ID의 비밀번호가 일치하지 않음 |
| `422` / `VALIDATION_ERROR` | 요청 body validation 실패 |

## BE Realtime WebSocket

BE 서버의 사용자-facing 실시간 통신 엔드포인트입니다. 운영 환경에서 HTTPS/TLS 앞단을 통해
노출할 때 클라이언트는 아래 path를 `wss://<host>/api/v1/ws/realtime`로 연결합니다.
로컬 개발에서는 `ws://127.0.0.1:8000/api/v1/ws/realtime`를 사용할 수 있습니다.
BE 서버에서 `GET /api/v1/ws-docs`를 호출하면 WebSocket API 전용 문서 페이지를 조회할 수 있습니다.

WebSocket 메시지는 JSON envelope를 사용합니다.

```json
{
  "type": "ping",
  "payload": {}
}
```

### `wss://<host>/api/v1/ws/realtime`

지원 메시지:

| Client `type` | Server `type` | Meaning |
| --- | --- | --- |
| `ping` | `realtime.pong` | 연결 확인. 서버는 받은 `payload`를 그대로 돌려줌 |

Response:

```json
{
  "type": "realtime.pong",
  "payload": {}
}
```

잘못된 JSON, envelope 형식 오류, 지원하지 않는 message type은 `error` envelope를 보낸 뒤
`VALIDATION_ERROR`의 WebSocket close code인 `1008`로 연결을 종료합니다.

```json
{
  "type": "error",
  "payload": {
    "success": false,
    "data": null,
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "요청 값이 올바르지 않습니다.",
      "details": {
        "reason": "unsupported_message_type",
        "type": "unknown"
      }
    }
  }
}
```

## Agent Health

에이전트 상태 확인용 엔드포인트입니다.

| Method | Path | Response |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/api/v1/health` | `{"status": "ok"}` |
