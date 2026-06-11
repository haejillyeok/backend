# API

## Common Response

HTTP API에서 사용하는 공통 응답 envelope입니다. HTTP API는 이 형태를 JSON으로 반환합니다.
BE `/api/v1/*` REST API는 이 envelope를 사용합니다. 운영 probe 성격의 root `/health`와
Backend-to-Agent 전용 Agent API는 별도 명시된 raw 응답 계약을 유지합니다.

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
| `AGENT_CLIENT_NOT_CONFIGURED` | `INTERNAL` | `503` | `1011` | BE의 Agent client 설정 누락 |
| `AGENT_HEALTH_UNAVAILABLE` | `INTERNAL` | `502` | `1011` | BE에서 Agent health API 호출 실패 |

## BE Health

서비스 상태 확인용 엔드포인트입니다.

| Method | Path | Response |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/api/v1/health` | `{"success": true, "data": {"status": "ok"}}` |

## BE Agent Health

BE가 Agent 서버의 versioned health API를 호출해 Agent 상태를 확인합니다. Agent 연결 정보와
공유 secret은 배포 환경에서 주입합니다.

### GET `/api/v1/agent/health`

Response:

```json
{
  "success": true,
  "data": {
    "status": "ok"
  }
}
```

| Status | Meaning |
| --- | --- |
| `200` | Agent health API 응답 성공 |
| `502` / `AGENT_HEALTH_UNAVAILABLE` | Agent health API 호출 실패, timeout, 비정상 응답 |
| `503` / `AGENT_CLIENT_NOT_CONFIGURED` | Agent client 설정 누락 |

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

BE 서버의 WebSocket 연결 테스트용 엔드포인트입니다. 운영 환경에서 HTTPS/TLS 앞단을 통해
노출할 때 클라이언트는 아래 path를 `wss://<host>/ws/realtime`로 연결해 ping/pong을 확인합니다.
로컬 개발에서는 `ws://127.0.0.1:8000/ws/realtime`를 사용할 수 있습니다.
BE 서버에서 `GET /ws-docs`를 호출하면 WebSocket API 전용 문서 페이지를 조회할 수 있습니다.

해질녘 게임의 실제 실시간 통신은 `/ws/realtime`을 확장하지 않고, 별도 `/ws/lobby`, `/ws/match`
계약으로 분리합니다.

WebSocket 메시지는 JSON envelope를 사용합니다.

```json
{
  "type": "ping",
  "payload": {}
}
```

### `wss://<host>/ws/realtime`

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

## Agent Authentication

Agent 비즈니스 API는 모든 요청에 아래 공유 키 header를 요구합니다. `/health` 계열에는 적용하지
않습니다.

```text
X-Agent-API-Key: <shared-secret>
```

서버의 `AGENT_API_KEY`가 설정되지 않으면 `503`, 값이 없거나 다르면 `401`을 반환합니다.

## Agent Answer

### POST `/api/v1/agent/answer`

Backend가 처리한 게임 상태를 받아 Qdrant의 검증된 후보 중 하나를 반환합니다. Agent는 턴, 라운드,
사람 입력 유효성, 투표, 마피아 규칙을 처리하지 않습니다.

```json
{
  "request_id": "req-20260610-0001",
  "room_id": "room-001",
  "game_type": "shiritori",
  "used_words": ["자전거", "거미줄"],
  "last_char": "줄",
  "ai_policy": {
    "allow_fake_mistake": false,
    "allow_reuse_word": false
  }
}
```

후보가 있으면:

```json
{
  "request_id": "req-20260610-0001",
  "room_id": "room-001",
  "game_type": "shiritori",
  "answer": "줄넘기",
  "status": "ok",
  "reason": null
}
```

후보가 없으면:

```json
{
  "request_id": "req-20260610-0001",
  "room_id": "room-001",
  "game_type": "shiritori",
  "answer": null,
  "status": "no_candidate",
  "reason": "no_available_word"
}
```

`game_type`은 `shiritori`, `chosung`, `contains`를 지원합니다. `condition.last_char`,
`condition.chosung`, `condition.contains_word`를 각각 사용하며, 끝말잇기는 기존 호환을 위해
root `last_char`도 허용합니다.

## Agent Data Stack

### POST `/api/v1/data/stack`

단어 목록을 정규화한 뒤 background task로 Qdrant에 적재합니다.

```json
{
  "request_id": "stack-20260610-0001",
  "source": "manual",
  "game_types": ["shiritori", "chosung", "contains"],
  "words": ["사과", "고구마밭", "줄넘기"],
  "options": {
    "is_valid": true,
    "is_banned": false,
    "overwrite_existing": false,
    "preserve_ai_used_count": true
  }
}
```

응답 status는 `202 Accepted`입니다.

```json
{
  "request_id": "stack-20260610-0001",
  "status": "accepted",
  "job_id": "job-9f81c2",
  "received_count": 3,
  "message": "word stack job accepted"
}
```
