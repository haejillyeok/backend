---
title: Realtime WebSocket
type: api-contract
updated: 2026-06-12
audience: ai
---

# Realtime WebSocket

BE 서버는 WebSocket 연결 테스트용 endpoint를 `/ws/realtime`에 둔다.
운영 HTTPS/TLS 앞단에서는 같은 path를 `wss://<host>/ws/realtime`로 연결한다.
로컬 개발에서는 `ws://127.0.0.1:8000/ws/realtime`를 사용한다.

`/ws/realtime`은 ping/pong과 envelope validation 확인을 위한 채널이다.
해질녘 게임의 실제 실시간 상태는 처음부터 `/ws/lobby/rooms/{room_public_id}`, `/ws/match`처럼
목적별 endpoint로 분리한다.

## Code Map

- Realtime endpoint: `app/be/api/endpoints/realtime_ws.py`
- Lobby endpoint: `app/be/api/endpoints/lobby_ws.py`
- HTML docs endpoint: `app/be/api/endpoints/ws_docs.py`
- Realtime connection manager and message handling: `app/be/services/realtime.py`
- Lobby connection manager and message handling: `app/be/services/lobby.py`
- Socket router include: `app/be/api/socket_router.py`
- Contract tests: `test/test_realtime_websocket.py`, `test/test_lobby_websocket.py`
- API-served docs source: `app/be/api/docs/ws-api.md`

## Docs Route

BE 서버는 WebSocket API 전용 문서 페이지를 `GET /ws-docs`에서 `text/html`로 반환한다.
문서 원본은 `app/be/api/docs/ws-api.md`이며, Docker image에 포함되도록 `docs/`가 아니라 `app/` 아래에서
관리한다. 라우터는 이 Markdown 원본을 HTML 페이지로 렌더링한다. WebSocket message contract가 늘어나면
이 파일을 먼저 갱신한다.

`/ws-docs` 렌더러는 heading을 anchor id로 변환하고 페이지 상단에 큰 섹션 중심 목차를 만든다.
목차는 문서 탐색용이므로 `##` 섹션만 보여주고, 개별 message type 같은 세부 heading은 본문 안에서
읽히게 둔다.
사용자 흐름이나 API/WebSocket 상호작용은 Markdown의 `mermaid` code block으로 작성할 수 있으며,
HTML 렌더러는 이를 Mermaid diagram으로 표시할 수 있게 `<pre class="mermaid">`와 초기화 스크립트를
포함한다.

`ws-api.md`는 한국어 사용자가 읽는 WebSocket reference 문서처럼 endpoint matrix, 공통 envelope,
message direction, endpoint별 message contract, error/close code를 분리해 작성한다. 본문은 한국어를
기본으로 쓰고, request/response/event 같은 영어 용어는 `요청(Request)`, `응답(Response)`,
`이벤트(Event)`처럼 보조 표기로 둔다.

유저 플로우는 하나의 큰 Mermaid diagram에 모두 넣지 않는다. 로비 연결, room 생성/참여,
게임 시작 handoff처럼 5~10 step 정도의 작은 Mermaid sequence diagram 여러 개로 나누어 관리한다.

## Message Contract

모든 메시지는 JSON envelope를 사용한다.

```json
{
  "type": "ping",
  "payload": {}
}
```

현재 지원하는 client message type은 `ping` 하나다. 서버는 같은 payload를 담아
`realtime.pong`을 반환한다.

```json
{
  "type": "realtime.pong",
  "payload": {}
}
```

잘못된 JSON, envelope 형식 오류, 지원하지 않는 message type은 `error` envelope를 보낸 뒤
`VALIDATION_ERROR`의 WebSocket close code인 `1008`로 연결을 닫는다.

## Lobby Contract

로비 목록 조회, 객실 생성, 객실 참여, 명시적 객실 퇴장은 REST API가 담당한다.

- `GET /api/v1/game/rooms`: 닫히지 않은 객실 목록, 활성 멤버 수, 현재 유저의 active room membership 여부, 참여 중인 유효 로비의 WebSocket 연결 path를 반환한다.
- `POST /api/v1/game/rooms`: 대기 객실을 만들고 방장을 첫 활성 room member로 등록한다.
- `POST /api/v1/game/rooms/{room_public_id}/join`: 대기 객실에 현재 유저를 활성 room member로 등록한다.
- `POST /api/v1/game/rooms/{room_public_id}/leave`: 대기 객실에서 현재 유저를 퇴장시키고, 방장 퇴장 시 가장 먼저 입장한 남은 활성 멤버에게 방장을 승계한다. 마지막 멤버가 나가면 room을 `closed` 처리하고 `closed_at`을 기록해 이후 목록, 참여, WebSocket 진입에서 제외한다.

`/ws/lobby/rooms/{room_public_id}`는 연결 수락 전에 `session_token` 쿠키로 로그인 세션을 확인하고,
path의 `room_public_id`와 user_id로 활성 `game.room_members` 존재 여부를 확인한다. 인증 실패, 객실
없음, 활성 멤버 아님은 `1008` close code로 닫는다. 성공하면 `lobby.room.connected` event로
`room_public_id`와 현재 유저 identity를 보내고, 이어서 `lobby.room.snapshot` event로 현재 활성
room member 목록을 `joined_at` 오름차순으로 보낸다. Snapshot member에는 `user_public_id`, `nickname`,
`is_owner`, `joined_at`을 담고, payload root에는 현재 `owner_user_public_id`를 둔다. 클라이언트는
방 화면 진입/재접속 시 snapshot으로 멤버 목록을 초기화하고 이후 `lobby.room.joined`,
`lobby.room.left` event로 변경분을 반영한다.

지원하는 client message type은 `ping` 하나이며, 같은 payload를 `lobby.pong`으로 반환한다. 별도
`lobby.subscribe_room`/`lobby.unsubscribe_room` 메시지는 사용하지 않는다. path의 room public_id가
연결과 동시에 이벤트 구독 범위가 된다.

room 로비 WebSocket은 client가 주기적으로 보내는 `ping`을 heartbeat로 본다. 서버는 마지막 메시지 이후
45초 동안 새 메시지가 없으면 연결을 닫는다. disconnect 시점에는 즉시 DB 퇴장 처리하지 않고 90초
grace leave task를 예약한다. 같은 유저가 같은 room으로 grace time 안에 재연결하면 task를 취소하고,
복귀하지 않으면 REST 퇴장과 같은 service 경로로 `game.room_members.left_at`, 방장 승계, 마지막 멤버
퇴장 시 room 폐쇄를 처리한 뒤 같은 room 연결에 `lobby.room.left` event를 broadcast한다.

REST commit 이후 server process 안의 lobby connection manager가 같은 room 연결에 event를
broadcast한다. `lobby.room.joined`는 신규 멤버가 추가된 경우(`already_member=false`)에만 보내고,
이미 참여 중인 반복 join 요청은 REST 응답만 반환한다. `lobby.room.left`는 REST 퇴장 또는
WebSocket grace leave로 퇴장이 확정된 경우 broadcast한다. WebSocket manager는 연결 상태만
process memory에 보관하며, room membership의 최종 사실은 DB다. Broadcast message는 특정 client
request의 응답이 아니므로 `응답(Response)`이 아니라 `이벤트(Event)`로 문서화한다.

## Design Notes

- TLS 자체는 FastAPI endpoint가 아니라 배포/프록시 계층에서 종단한다.
- `/ws/realtime`은 게임 상태를 소유하거나 브로드캐스트하지 않는다.
- 실제 게임용 WebSocket은 기능별 endpoint와 connection manager를 별도로 둔다.
- 앱 코드는 각 WebSocket endpoint와 JSON message contract를 소유한다.
- Connection manager는 active connection registry와 cleanup을 담당한다.
- 이후 세션 인증이 필요하면 연결 수락 전 쿠키 또는 token을 검증하고, 인증 실패는 `1008` close code로 닫는다.

## Related

- [backend-guidelines.md](backend-guidelines.md)
- [code-conventions.md](code-conventions.md)
- [decisions/2026-06-11-split-lobby-match-websockets.md](decisions/2026-06-11-split-lobby-match-websockets.md)
