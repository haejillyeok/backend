---
title: Realtime WebSocket
type: api-contract
updated: 2026-06-13
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
- Match endpoint: `app/be/api/endpoints/match_ws.py`
- HTML docs endpoint: `app/be/api/endpoints/ws_docs.py`
- Realtime connection manager and message handling: `app/be/services/realtime.py`
- Lobby connection manager and message handling: `app/be/services/lobby.py`
- Match connection manager and snapshot/message handling: `app/be/services/match.py`
- Match progress event service: `app/be/services/match_progress.py`
- Match vote/result service: `app/be/services/match_vote.py`
- Socket router include: `app/be/api/socket_router.py`
- Contract tests: `test/test_realtime_websocket.py`, `test/test_lobby_websocket.py`, `test/test_match_websocket.py`
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
- `PATCH /api/v1/game/rooms/{room_public_id}`: 방장이 대기 객실 설정을 수정하고, 성공 후 같은 객실 연결에 `lobby.room.updated`를 broadcast한다.
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

## Match Contract

`/ws/match`는 `session_token + game_session_public_id` 또는 재접속용 `game_session_token`으로
participant identity를 복원한다. 연결 직후 `match.connected`, `match.snapshot`을 보낸다. Snapshot과
event payload는 익명 표시명과 seat number만 공개하고, 원래 닉네임, user id, AI 여부는 노출하지 않는다.
끝말잇기 세션 시작 transaction은 첫 번째 `turn` phase와 `word_game.turns` row를 함께 만들고,
`game_sessions.current_phase_id`를 이 phase로 지정한다. 따라서 match snapshot은 현재 phase를 조회해
`current_turn.phase_id`, `round_number`, `turn_number`, `actor_seat_number`, `deadline_at`,
`required_start_char`를 복구한다. `phase_id`는 client가 `word.submit.phase_id`로 다시 보내는 현재 턴
식별자다. 첫 턴은 `round_number=1`, `turn_number=1`, `required_start_char=null`이다.

현재 client command는 `ping`, `word.submit`, `vote.submit`이다. `ping`은 `match.pong`으로 응답한다. `word.submit`은
연결 identity의 participant, payload의 `phase_id`, 서버 시각, DB current phase/turn/deadline/used_words를
기준으로 검증한다. 성공하면 `participant_actions.action_type = word_submit`, `word_game.submissions`,
`word_game.used_words`, `score_ledger`, `game_events.event_type = word.accepted`를 저장하고 다음
`turn` phase와 `word_game.turns` row를 만든 뒤 `game_sessions.current_phase_id`를 다음 phase로 옮긴다.
commit 이후 같은 game session 연결에 `match.word.accepted`를 broadcast한다. 시작 글자 불일치, 중복 단어처럼
게임 규칙상 거절된 제출은 WebSocket 오류가 아니라 게임 안의 공개 판정으로 다룬다.
`participant_actions.action_type = word_reject`, `score_ledger`, `game_events.event_type = word.rejected`를
저장하고 commit 이후 `match.word.rejected`를 broadcast하며, 현재 턴은 유지한다. 지원하지 않는 message type은
`error` envelope 후 `VALIDATION_ERROR`의 close code `1008`로 닫는다.

턴 제한 시간 초과는 client timer가 아니라 서버 `deadline_at` 기준으로 확정한다. `/ws/match` loop는
heartbeat 대기 시간과 현재 턴 deadline 중 더 이른 시점까지만 client frame을 기다리고, deadline이 먼저
도달하면 Backend가 이미 끝난 phase가 아니고 deadline이 지난 current phase를
`participant_actions.action_type = turn_timeout`, `game_events.event_type = turn_timeout`,
`session_phases.result_status = timeout`으로 저장하고, commit 이후 같은 game session의 match 연결에
`match.turn.timeout`을 broadcast한다. deadline 이후 도착한 `word.submit`도 WebSocket 연결 오류가 아니라
같은 timeout 확정 경로로 처리해 `match.turn.timeout`을 broadcast하고 연결은 유지한다.
Timeout으로 끝말잇기 한판이 종료되면 event payload에 남은 판의 첫 턴인 `next_turn` 또는 모든 판 종료 후
투표 전환을 뜻하는 `next_status=voting`과 `voting_deadline_at`을 포함한다. 투표 전환 시 Backend는
`phase_type=voting`인 `session_phases` row를 만들고 `game_sessions.current_phase_id`로 지정해 재접속
snapshot에서 deadline을 복구할 수 있게 한다.

AI 손님의 차례에서 Agent API가 timeout, 네트워크 오류, 4xx/5xx, invalid payload, `no_candidate` 등으로
단어를 확정하지 못하면 Backend가 실패를 확정한다. 실패는 `participant_actions.action_type =
ai_answer_failed`, `game_events.event_type = ai_answer_failed`로 저장하고, transaction commit 이후 같은
game session의 match 연결에 `match.turn.failed`를 broadcast한다. WebSocket send는 DB transaction 안에서
실행하지 않는다.
AI 실패로 끝말잇기 한판이 종료되는 경우에도 timeout과 같은 전환 규칙을 적용해 `next_turn` 또는
`next_status=voting`, `voting_deadline_at`을 event payload에 포함한다.
Agent 호출은 DB transaction 밖에서 대기하므로, 서버 timeout 등으로 이미 종료된 phase에 대해 뒤늦게
AI 성공 또는 실패가 돌아오면 추가 action/event 없이 무시한다.
AI가 성공 답변을 가져왔더라도 `submit_word` 시점에 서버 deadline이 이미 지났다면 단어 제출로 저장하지
않고 `turn_timeout` 확정 경로로 `match.turn.timeout`을 broadcast한다.

AI 턴 처리는 Agent API 호출을 DB 쓰기 transaction과 분리한다. 먼저 DB에서 현재 phase가 AI actor인지,
`used_words`, `required_start_char`를 조회하고, Agent `/api/v1/agent/answer`에 `used_words`, `last_char`,
`condition.last_char`를 보낸다. `status=ok`와 answer가 있으면 기존 `submit_word` 진행 경로로 저장하고,
`no_candidate` 또는 Agent client 오류는 기존 `fail_ai_answer` 진행 경로로 저장한다.
`/ws/match`의 `word.submit` 처리 후 `match.word.accepted.next_turn.phase_id`가 있으면 optional AI turn
service가 해당 phase를 확인한다. Agent answer 설정이 없으면 match 연결과 사용자 제출은 계속 동작하고,
설정이 있으면 AI actor인 경우에만 이어서 AI 결과 event를 broadcast한다.

`voting` 상태의 snapshot은 `voting_deadline_at`을 포함한다. `/ws/match` loop는 turn deadline과 같은 방식으로
투표 deadline을 기다리고, deadline이 먼저 도달하면 제출된 투표만 반영해 `match.vote.timeout`과
`match.result.published`를 broadcast한다. `vote.submit` payload는 익명성을 유지하기 위해 participant UUID가
아니라 `target_seat_number`만 받는다. Backend는 연결 participant를 voter로 고정하고, session 안의
seat number를 target participant로 해석한다. 투표 저장 후 `match.vote.accepted`를 broadcast하되 다른
참가자의 선택을 누설하지 않도록 target은 포함하지 않고 투표자와 제출 현황만 보낸다. 모든 실제 유저가
투표하면 Backend가 투표 점수와 최종 순위를 저장하고 `match.result.published`를 broadcast한다. 결과
event에서만 `revealed_participant_type`으로 `user`/`ai`를 공개한다. 미투표자는 투표 점수 0점으로 남긴다.
deadline 이후 도착한 `vote.submit`은 저장하지 않고 WebSocket 연결 오류도 내지 않으며, 같은 timeout 확정
경로로 `match.vote.timeout`과 `match.result.published`를 broadcast한다.
여러 `/ws/match` 연결의 timer가 같은 voting deadline을 감지할 수 있으므로, 이미 `result` 상태가 된 세션의
stale vote timeout 시도는 추가 event 없이 무시한다.
결과 확정 이후 재접속한 client를 위해 `match.snapshot`은 `results` 배열에 `session_results` 기반 최종 점수,
순위, 우승 여부, 공개 participant type, vote score delta, `is_me`를 포함한다.

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
