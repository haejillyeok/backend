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

## Session Authentication

BE REST API는 public router와 protected router를 분리합니다.

- Public: `GET /health`, `GET /api/v1/health`, `GET /api/v1/agent/health`, `POST /api/v1/auth/login`, `POST /api/v1/auth/signup`
- Protected: 게임 세션 등 로그인 유저 권한이 필요한 `/api/v1/*` API

Protected router는 `session_token` HttpOnly 쿠키를 공통 dependency에서 검증합니다. 세션 토큰 원문은
SHA-256 hash로 변환해 `users.user_sessions.token_hash`와 비교하고, `revoked_at IS NULL`,
`expires_at > now`인 세션만 허용합니다. 통과하면 서버가 `CurrentUser`를 복원하며, 각 endpoint는
필요할 때 이 `CurrentUser.id`로 도메인 권한을 확인합니다.

새 BE API를 추가할 때 로그인/헬스처럼 공개되어야 하는 API만 public router에 넣고, 기본은 protected
router에 등록합니다. endpoint 본문에서 유저 ID가 필요하면 같은 `get_current_user` dependency를
파라미터로 주입받아 사용합니다.

### Error Codes

| Code | Type | HTTP | WebSocket | Meaning |
| --- | --- | --- | --- | --- |
| `INVALID_CREDENTIALS` | `AUTHENTICATION` | `401` | `1008` | 계정 ID가 없거나 비밀번호가 일치하지 않음 |
| `AUTH_USER_CONFLICT` | `CONFLICT` | `409` | `1008` | 회원가입 계정 ID 또는 닉네임 중복 |
| `SESSION_EXPIRED` | `AUTHENTICATION` | `401` | `1008` | 세션 쿠키 없음 또는 세션 만료/폐기. 쿠키가 없으면 `로그인이 필요합니다.`, 쿠키는 있지만 활성 세션이 아니면 `세션이 만료되었습니다.` 메시지를 반환 |
| `VALIDATION_ERROR` | `VALIDATION` | `422` | `1008` | 요청 body validation 실패 |
| `HTTP_ERROR` | `INTERNAL` | `500` | `1011` | FastAPI `HTTPException` fallback |
| `AGENT_CLIENT_NOT_CONFIGURED` | `INTERNAL` | `503` | `1011` | BE의 Agent client 설정 누락 |
| `AGENT_HEALTH_UNAVAILABLE` | `INTERNAL` | `502` | `1011` | BE에서 Agent health API 호출 실패 |
| `GAME_ROOM_NOT_FOUND` | `NOT_FOUND` | `404` | `1008` | 게임을 시작할 객실을 찾을 수 없음 |
| `GAME_ROOM_START_FORBIDDEN` | `AUTHORIZATION` | `403` | `1008` | 방장 또는 허용된 멤버가 아닌 유저의 게임 시작 요청 |
| `GAME_ROOM_NOT_STARTABLE` | `CONFLICT` | `409` | `1008` | 현재 객실 상태나 멤버 조건에서 게임 시작 불가 |
| `GAME_ROOM_NOT_JOINABLE` | `CONFLICT` | `409` | `1008` | 현재 객실 상태나 정원 조건에서 객실 참여 불가 |
| `GAME_ROOM_UPDATE_FORBIDDEN` | `AUTHORIZATION` | `403` | `1008` | 방장이 아닌 유저의 객실 설정 수정 요청 |
| `GAME_ROOM_NOT_UPDATEABLE` | `CONFLICT` | `409` | `1008` | 현재 객실 상태나 멤버 조건에서 객실 설정 수정 불가 |
| `GAME_ROOM_ENTRY_FORBIDDEN` | `AUTHORIZATION` | `403` | `1008` | 활성 room member가 아닌 유저의 객실 로비 WebSocket 연결 요청 |
| `GAME_SESSION_ENTRY_FORBIDDEN` | `AUTHORIZATION` | `403` | `1008` | 게임 시작 시 확정된 참가자가 아닌 유저의 세션 진입 요청 |

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

회원가입과 로그인을 별도 API로 처리합니다. 로그인은 기존 계정의 `account_id`, `password`만 검증하고
신규 유저를 만들지 않습니다. 회원가입은 `account_id`, `nickname`, `password`를 받아 새 유저를 만들고,
계정 ID와 닉네임은 타 유저와 중복될 수 없습니다.

- 계정 ID: 영어 문자, 숫자, `_`만 허용, 3~20자
- 비밀번호: 한글, 영어, 숫자, 특수자 입력 가능, 8~20자
- 닉네임: 한글, 영어, 숫자, `_`만 허용, 3~20자

### POST `/api/v1/auth/login`

Request:

```json
{
  "account_id": "player_001",
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
    "expires_at": "2026-06-12T00:00:00+09:00"
  }
}
```

성공하면 `session_token` 쿠키를 설정합니다. 로컬/dev 환경에서는 `HttpOnly`, `SameSite=Lax`로 발급하고,
`prod` 환경에서는 로컬 테스트 페이지처럼 다른 site에서 운영 API를 호출하는 credential 요청도 허용하기
위해 `HttpOnly`, `SameSite=None`, `Secure`를 함께 사용합니다.

| Status | Meaning |
| --- | --- |
| `200` | 로그인 성공 |
| `401` / `INVALID_CREDENTIALS` | 계정 ID가 없거나 비밀번호가 일치하지 않음 |
| `422` / `VALIDATION_ERROR` | 요청 body validation 실패 |

### POST `/api/v1/auth/signup`

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
    "expires_at": "2026-06-12T00:00:00+09:00"
  }
}
```

성공하면 `session_token` 쿠키를 설정합니다. 로컬/dev 환경에서는 `HttpOnly`, `SameSite=Lax`로 발급하고,
`prod` 환경에서는 로컬 테스트 페이지처럼 다른 site에서 운영 API를 호출하는 credential 요청도 허용하기
위해 `HttpOnly`, `SameSite=None`, `Secure`를 함께 사용합니다.

| Status | Meaning |
| --- | --- |
| `201` | 회원가입 성공 |
| `409` / `AUTH_USER_CONFLICT` | 계정 ID 또는 닉네임 중복 |
| `422` / `VALIDATION_ERROR` | 요청 body validation 실패 |

## BE Game Session

게임 진행 WebSocket을 연결하기 전에 REST API로 게임 세션을 시작하고 진입 권한을 확인합니다.
인증은 `session_token` HttpOnly 쿠키를 사용합니다. 게임 시작 시점의 활성 room member만
`session_participants`로 고정되고, 이후 세션 진입 API는 로그인 유저가 해당 참가자인지 확인합니다.
게임 시작과 진입 확인 응답은 로그인 세션과 별개인 `game_session_token`을 함께 반환합니다. 이 토큰은
현재 로그인 유저에게 매핑된 `session_participants` 행에만 연결되는 match 복구 credential이며, 원문은
응답으로 한 번 내려가고 DB에는 SHA-256 hash와 만료 시각만 저장합니다.
`/ws/realtime`은 연결 테스트용으로 유지하며 이 API와 게임 상태를 공유하지 않습니다.

로비의 영속 상태는 DB의 `game.rooms`, `game.room_members`로 관리합니다. 객실 목록 조회, 객실 생성,
객실 참여는 REST API가 담당하고, `/ws/lobby/rooms/{room_public_id}`는 로그인 세션과 활성 room member
여부를 연결 시점에 확인한 뒤 현재 연결만 process memory에 보관합니다. REST API가 DB 변경을 commit한
뒤 필요한 event를 같은 객실 연결에 broadcast합니다.

Swagger에는 게임 API의 닫힌 문자열 값을 enum으로 노출합니다.

| Field | Values |
| --- | --- |
| `game_type` | `shiritori`, `chosung`, `contains` |
| room `status` | `waiting`, `starting`, `playing`, `closed` |
| game session `status` | `starting`, `playing`, `voting`, `result`, `aborted` |

게임 진행 중 public participant payload는 익명 처리된 `display_name`과 `seat_number`만 노출합니다.
`participant_type`, `is_uninvited_guest`, 원래 닉네임은 결과 공개 전까지 REST/WebSocket 공통 payload에
포함하지 않습니다.

로비 WebSocket 클라이언트는 주기적으로 `ping`을 보내야 합니다. 서버는 마지막 메시지 이후 45초 동안
새 메시지를 받지 못하면 연결을 닫고, 90초 grace time 안에 같은 유저가 같은 방으로 재연결하지 않으면
`room_members.left_at`을 기록해 퇴장 처리합니다. 퇴장 확정 후 같은 방 연결에는 `lobby.room.left`
event를 broadcast합니다.

이후 `/ws/lobby/rooms/{room_public_id}`를 붙일 때는 게임 시작 API handler가 DB commit 이후
lobby connection manager를 호출해 이미 열려 있는 room 연결에 `game.started` event를 broadcast합니다.
API가 WebSocket 연결 객체를 클라이언트에 전달하는 것이 아니라, 서버 process 안의 connection registry에서
`room_public_id -> websocket` 형태로 잡고 있는 연결들에 event를 송신하는 방식입니다.
여러 서버 instance로 확장하면 같은 event를 Redis Pub/Sub, PostgreSQL NOTIFY, outbox 같은
서버 간 event bus로 발행한 뒤 각 instance가 자신이 가진 WebSocket 연결에 broadcast해야 합니다.

`/ws/match` 연결 시점에는 유효한 `session_token`과 `game_session_public_id` 조합으로 참가자를 확인하거나,
이미 발급받은 `game_session_token`으로 참가자 identity를 복원합니다. 연결이 성립하면 서버 내부
connection identity는 `game_session_id + participant_id + user_id`로 고정합니다. 연결 후 match 진행
메시지는 이 participant identity를 기준으로 처리하고, 로그인 세션 만료가 진행 중 match를 즉시 끊는
기준이 되지는 않습니다. 새 lobby 연결, 새 게임 시작 같은 새 계정 권한 행위는 다시 유효한 로그인
세션이 필요합니다.

### GET `/api/v1/game/rooms`

로그인 유저가 로비에서 선택할 수 있는 닫히지 않았고 활성 멤버가 1명 이상인 객실 목록을 조회합니다.
이 API는 목록 snapshot만 반환합니다. 특정 객실의 실시간 이벤트는 참여가 허용된 뒤
`/ws/lobby/rooms/{room_public_id}`로 연결해 수신합니다.

Response:

```json
{
  "success": true,
  "data": {
    "rooms": [
      {
        "room_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e",
        "name": "첫 객실",
        "game_type": "shiritori",
        "status": "waiting",
        "max_players": 4,
        "member_count": 1,
        "is_current_user_member": true,
        "is_current_user_owner": true,
        "lobby_websocket_path": "/ws/lobby/rooms/018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e"
      }
    ],
    "current_membership": {
      "room_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e",
      "name": "첫 객실",
      "game_type": "shiritori",
      "status": "waiting",
      "max_players": 4,
      "member_count": 1,
      "is_owner": true,
      "lobby_websocket_path": "/ws/lobby/rooms/018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e"
    }
  }
}
```

| Status | Meaning |
| --- | --- |
| `200` | 객실 목록 조회 성공 |
| `401` / `SESSION_EXPIRED` | 로그인 세션 없음, 만료, 폐기 |

### POST `/api/v1/game/rooms`

로그인 유저를 방장으로 하는 대기 객실을 만들고, 같은 transaction에서 방장을 첫 활성
`room_members`로 등록합니다. 성공 후 클라이언트는 응답의 `room_public_id`로
`/ws/lobby/rooms/{room_public_id}`에 연결할 수 있습니다.

Request:

```json
{
  "name": "첫 객실",
  "game_type": "shiritori",
  "max_players": 4
}
```

Response:

```json
{
  "success": true,
  "data": {
    "room_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e",
    "name": "첫 객실",
    "game_type": "shiritori",
    "status": "waiting",
    "max_players": 4,
    "member_count": 1,
    "created_at": "2026-06-12T00:00:00+09:00"
  }
}
```

| Status | Meaning |
| --- | --- |
| `201` | 객실 생성 성공 |
| `401` / `SESSION_EXPIRED` | 로그인 세션 없음, 만료, 폐기 |
| `422` / `VALIDATION_ERROR` | 요청 body validation 실패 |

### PATCH `/api/v1/game/rooms/{room_public_id}`

방장이 대기 중인 객실의 이름, 최대 실제 유저 수, 게임 시작 전 룰 설정을 수정합니다. 이 API는
`waiting` 상태에서만 허용되며 현재 활성 멤버 수보다 작은 `max_players`로 줄일 수 없습니다.
성공 후 서버는 같은 room의 `/ws/lobby/rooms/{room_public_id}` 연결에 `lobby.room.updated` event를
broadcast합니다.

Request:

```json
{
  "name": "수정된 객실",
  "max_players": 5,
  "rule_config": {
    "max_rounds": 8,
    "turn_time_seconds": 10
  }
}
```

Response:

```json
{
  "success": true,
  "data": {
    "room_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e",
    "name": "수정된 객실",
    "game_type": "shiritori",
    "status": "waiting",
    "max_players": 5,
    "rule_config": {
      "max_rounds": 8,
      "turn_time_seconds": 10
    }
  }
}
```

| Status | Meaning |
| --- | --- |
| `200` | 객실 설정 수정 성공 |
| `401` / `SESSION_EXPIRED` | 로그인 세션 없음, 만료, 폐기 |
| `403` / `GAME_ROOM_UPDATE_FORBIDDEN` | 방장이 아닌 유저 |
| `404` / `GAME_ROOM_NOT_FOUND` | 객실 없음 |
| `409` / `GAME_ROOM_NOT_UPDATEABLE` | 객실이 대기 상태가 아니거나 설정 조건 불충족 |
| `422` / `VALIDATION_ERROR` | 요청 body 또는 path UUID validation 실패 |

### POST `/api/v1/game/rooms/{room_public_id}/join`

로그인 유저를 대기 중인 객실의 활성 `room_members`로 참여시킵니다. 이미 같은 room에 활성 멤버로
참여 중이면 새 row를 만들지 않고 기존 참여 정보를 반환하므로 반복 요청에 멱등적으로 동작합니다.
객실이 대기 상태가 아니거나 정원이 가득 찬 경우에는 참여할 수 없습니다.

신규 멤버로 추가된 경우(`already_member=false`) 서버는 같은 room의
`/ws/lobby/rooms/{room_public_id}` 연결에 `lobby.room.joined` event를 broadcast합니다. 이미 참여
중인 반복 요청은 응답만 반환하고 별도 WebSocket event를 보내지 않습니다.

Response:

```json
{
  "success": true,
  "data": {
    "room_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e",
    "user_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7f",
    "nickname": "초보자",
    "joined_at": "2026-06-12T00:00:00+09:00",
    "already_member": false
  }
}
```

| Status | Meaning |
| --- | --- |
| `200` | 객실 참여 성공 또는 이미 참여 중 |
| `401` / `SESSION_EXPIRED` | 로그인 세션 없음, 만료, 폐기 |
| `404` / `GAME_ROOM_NOT_FOUND` | 객실 없음 |
| `409` / `GAME_ROOM_NOT_JOINABLE` | 객실이 대기 상태가 아니거나 정원 초과 |
| `422` / `VALIDATION_ERROR` | path UUID validation 실패 |

### POST `/api/v1/game/rooms/{room_public_id}/leave`

로그인 유저를 대기 중인 객실의 활성 `room_members`에서 퇴장시킵니다. 방장이 나갔고 남은 활성 멤버가
있으면 가장 먼저 입장한 남은 멤버에게 방장을 승계합니다. 마지막 멤버가 나가면 room을 `closed`로
바꾸고 `closed_at`을 기록해 목록, 참여, 로비 WebSocket 진입에서 제외합니다.

성공 후 서버는 같은 room의 `/ws/lobby/rooms/{room_public_id}` 연결에 `lobby.room.left` event를
broadcast합니다.

Response:

```json
{
  "success": true,
  "data": {
    "room_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e",
    "user_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7f",
    "nickname": "초보자",
    "left_at": "2026-06-12T00:00:00+09:00",
    "remaining_member_count": 1,
    "new_owner_user_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b80",
    "new_owner_nickname": "다음방장",
    "room_closed": false
  }
}
```

| Status | Meaning |
| --- | --- |
| `200` | 객실 퇴장 성공 |
| `401` / `SESSION_EXPIRED` | 로그인 세션 없음, 만료, 폐기 |
| `403` / `GAME_ROOM_ENTRY_FORBIDDEN` | 현재 유저가 활성 room member가 아님 |
| `404` / `GAME_ROOM_NOT_FOUND` | 객실 없음 |
| `409` / `GAME_ROOM_NOT_JOINABLE` | 객실이 대기 상태가 아님 |
| `422` / `VALIDATION_ERROR` | path UUID validation 실패 |

### POST `/api/v1/game/rooms/{room_public_id}/start`

방장이 대기 중인 객실의 활성 멤버를 게임 세션 참가자로 고정하고, 클라이언트가 이후 진입 확인에
사용할 `game_session_public_id`를 반환합니다. 실제 유저 참가자 뒤에 AI 손님 1명이
내부 참가자로 추가됩니다. 시작 시점의 객실 `rule_config`는 `game_sessions.rule_config`에 snapshot으로
고정됩니다. `game_session_public_id`는 한 게임 세션의 공개 식별자이며, 라운드 ID가 아닙니다.

이 endpoint는 방장의 반복 요청에 대해 멱등적으로 동작합니다. 같은 room에 `starting`, `playing`,
`voting`처럼 아직 종료되지 않은 active session이 있으면 새 session을 만들지 않고 기존
`game_session_public_id`와 참가자 snapshot을 반환합니다. 이때 현재 요청 유저의 `game_session_token`은
새로 발급해 응답합니다. 서버는 시작 판단 전에 room row를 lock해서 동시 start 요청이 같은 room 안에서
직렬화되도록 처리합니다.

Response:

```json
{
  "success": true,
  "data": {
    "game_session_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7f",
    "room_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e",
    "game_type": "shiritori",
    "status": "starting",
    "game_session_token": "opaque-game-session-token",
    "game_session_token_expires_at": "2026-06-12T03:00:00+09:00",
    "rule_config": {
      "max_rounds": 8,
      "turn_time_seconds": 10
    },
    "participants": [
      {
        "display_name": "1번 손님",
        "seat_number": 1
      },
      {
        "display_name": "2번 손님",
        "seat_number": 2
      }
    ]
  }
}
```

| Status | Meaning |
| --- | --- |
| `200` | 게임 세션 시작 성공 |
| `401` / `SESSION_EXPIRED` | 로그인 세션 없음, 만료, 폐기 |
| `403` / `GAME_ROOM_START_FORBIDDEN` | 방장 또는 활성 room member가 아닌 유저 |
| `404` / `GAME_ROOM_NOT_FOUND` | 객실 없음 |
| `409` / `GAME_ROOM_NOT_STARTABLE` | 객실이 대기 상태가 아니거나 시작 조건 불충족 |
| `422` / `VALIDATION_ERROR` | path UUID validation 실패 |

### GET `/api/v1/game/sessions/{game_session_public_id}/entry`

로그인 유저가 게임 시작 시 `session_participants`에 고정된 실제 유저 참가자인지 확인합니다.
허용된 멤버만 `allowed=true` 응답을 받으며, AI 참가자는 로그인 유저가 아니므로 이 API로 직접
진입하지 않습니다.

Response:

```json
{
  "success": true,
  "data": {
    "game_session_public_id": "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7f",
    "allowed": true,
    "game_session_token": "opaque-game-session-token",
    "game_session_token_expires_at": "2026-06-12T03:00:00+09:00",
    "participant": {
      "display_name": "1번 손님",
      "seat_number": 1
    }
  }
}
```

| Status | Meaning |
| --- | --- |
| `200` | 게임 세션 진입 허용 |
| `401` / `SESSION_EXPIRED` | 로그인 세션 없음, 만료, 폐기 |
| `403` / `GAME_SESSION_ENTRY_FORBIDDEN` | 해당 게임 세션에 고정된 참가자가 아님 |
| `422` / `VALIDATION_ERROR` | path UUID validation 실패 |

## BE Realtime WebSocket

BE 서버의 WebSocket 연결 테스트용 엔드포인트입니다. 운영 환경에서 HTTPS/TLS 앞단을 통해
노출할 때 클라이언트는 아래 path를 `wss://<host>/ws/realtime`로 연결해 ping/pong을 확인합니다.
로컬 개발에서는 `ws://127.0.0.1:8000/ws/realtime`를 사용할 수 있습니다.
BE 서버에서 `GET /ws-docs`를 호출하면 WebSocket API 전용 문서 페이지를 조회할 수 있습니다.

해질녘 게임의 실제 실시간 통신은 `/ws/realtime`을 확장하지 않고, 별도
`/ws/lobby/rooms/{room_public_id}`, `/ws/match` 계약으로 분리합니다.

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

Backend가 처리한 게임 상태를 받아 Qdrant 후보를 우선 반환합니다. Agent는 턴, 라운드,
사람 입력 유효성, 투표, 마피아 규칙을 처리하지 않습니다.

```json
{
  "request_id": "req-20260610-0001",
  "room_id": "room-001",
  "game_type": "shiritori",
  "used_words": ["자전거", "거미줄"],
  "last_char": "줄",
  "condition": {
    "last_char": "줄"
  },
  "ai_policy": {
    "allow_fake_mistake": false,
    "allow_reuse_word": false
  }
}
```

Qdrant 후보가 있으면 `used_words`를 제외한 후보 중 최대 10개를 무작위로 추리고, 그중 하나를
무작위로 반환합니다.

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

끝말잇기 Qdrant 후보가 없으면 vLLM을 한 번 호출해 `last_char`로 시작하는 완성형 한글
2~4글자 단어를 생성합니다. 생성 결과가 시작 글자, 길이, 한글 형식, `used_words` 제외 조건을
모두 통과하면 동일한 `status=ok` 응답으로 반환합니다. 생성 단어는 자동으로 Qdrant에 적재하지
않습니다.

vLLM이 비활성화됐거나, 호출에 실패했거나, 생성 결과가 검증을 통과하지 못하면:

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
root `last_char`도 허용합니다. Qdrant 후보가 없으면 세 game type 모두 각각의 조건을 검증하는
vLLM 생성 fallback을 한 번 호출합니다.

## Agent Data Stack

### POST `/api/v1/data/stack`

단어 목록을 정규화한 뒤 background task로 Qdrant에 적재합니다.

```json
{
  "request_id": "stack-20260610-0001",
  "source": "manual",
  "words": ["사과", "고구마밭", "줄넘기"],
  "options": {
    "overwrite_existing": false,
    "preserve_used_count": true
  }
}
```

검증 완료 단어만 적재하며 Qdrant payload는 다음 필드만 사용합니다.

```json
{
  "word": "사과",
  "start_word": "사",
  "end_word": "과",
  "chosung": "ㅅㄱ",
  "syllables": ["사", "과"],
  "length": 2,
  "used_count": 0
}
```

기존 client의 `game_types`, `is_valid`, `is_banned` 입력은 무시하며
`preserve_ai_used_count`는 `preserve_used_count`의 호환 입력으로 허용합니다.

검증 완료 JSONL을 직접 적재할 때는 `scripts/seed_word_payloads.py`를 사용합니다. 파일을
스트리밍 검증하고 기본 500개 단위로 Qdrant에 upsert합니다.

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
