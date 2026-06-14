---
title: Sunset Game Domain
type: domain-model
updated: 2026-06-14
audience: ai
---

# Sunset Game Domain

`해질녘(SUNSET)`은 호텔 테마의 웹 기반 모바일 반응형 멀티플레이어 게임이다.
플레이어는 로비에서 객실에 입장해 단어 게임을 진행하고, 게임 종료 후 함께 플레이한 손님 중
초대받지 않은 손님인 AI 플레이어를 투표로 찾아낸다.

이 페이지는 캡처 기획안을 AI 작업 기준으로 컴파일한 도메인 모델이다. 구현 시 화면 목록보다
Backend가 소유하는 게임 상태, WebSocket event, Agent 경계를 우선한다.

## Product Contract

- `/ws/realtime`은 연결 테스트용 ping/pong endpoint로만 사용한다.
- 실제 게임 실시간 통신은 처음부터 BE `/ws/lobby/rooms/{room_public_id}`, `/ws/match` WebSocket으로 분리한다.
- 클라이언트는 서버 snapshot/event를 렌더링하고, 게임 상태의 최종 사실은 Backend가 가진다.
- Agent는 AI 손님의 단어 후보를 제공한다. 방, 턴, 라운드, 점수, 투표, 승패 계산은 Backend 책임이다.
- 게임 시작 시 AI 플레이어가 `Uninvited Guest`로 추가된다. 대기방에서 AI를 미리 포함시킬 필요는 없다.
- 게임 시작 후 닉네임은 가면 처리된 표시명으로 가려질 수 있다.

## Core Concepts

- `User`: 로그인 가능한 계정. 기존 users 도메인의 account_id, password, nickname 기준을 따른다.
- `Guest`: 객실 안의 참가자 단위. 실제 User 또는 AI 손님일 수 있다.
- `Uninvited Guest`: AI Guest. 플레이어는 게임 후 투표로 이 Guest를 찾아낸다.
- `Lobby`: 객실 목록, 객실 만들기, 객실 찾기, 빠른 입장, 친구 손님 리스트, 게임 종류 필터를 제공하는 공간.
- `Room`: 참가자가 대기하고 게임 세션을 시작하는 객실. 현재 MVP는 방 ID, 이름, 게임 종류, 참가자, 설정, 상태를 가진다. 준비 상태와 채팅은 확장 후보이다.
- `GameSession`: 한 객실에서 시작되어 결과가 확정될 때까지의 실행 단위. AI 추가, 가면 처리, 라운드, 턴, 사용 단어, 점수, 투표를 포함한다.
- `Round`: 끝말잇기 한판. `max_rounds=8`이면 한 게임 세션에서 끝말잇기 판을 최대 8번 진행한 뒤 투표로 넘어간다.
- `Cycle`: 한 Round 안에서 모든 Guest가 한 번씩 Turn을 가진 한 바퀴. Cycle은 Round가 아니며, Round 종료 조건이 만족될 때까지 같은 Round 안에서 여러 Cycle이 이어질 수 있다.
- `Turn`: 특정 Guest가 제한 시간 안에 입력해야 하는 차례. 시작 시각, 제한 시간, 조건, 제출, 성공/실패 결과를 가진다.
- `Submission`: Turn 중 입력된 단어와 검증 결과.
- `ScoreLedger`: 점수 변경 사유별 기록. 최종 점수만 저장하지 않고 사유를 함께 보존한다.
- `Vote`: 게임 종료 후 AI 손님을 지목하는 투표. 투표 시간은 20초 기준이다.

## User Flow

1. 로그인
2. 로비
3. 방 입장
4. 대기와 방 설정 수정
5. 게임 시작과 가면 처리
6. 게임 진행
7. 모든 라운드 종료 후 AI 지목 투표
8. 총점 계산과 우승자 발표

## REST Session Gate

게임 진행 WebSocket을 붙이기 전에는 REST API로 게임 시작과 세션 진입 권한을 먼저 고정한다.

게임 API의 공개 계약에서 닫힌 문자열 값은 Pydantic enum으로 관리해 Swagger에 enum으로 노출한다.

- `game_type`: `shiritori`, `chosung`, `contains`
- room `status`: `waiting`, `starting`, `playing`, `closed`
- game session `status`: `starting`, `playing`, `voting`, `result`, `aborted`
- `participant_type`: `user`, `ai`

- `GET /api/v1/game/rooms`
  - `session_token` 쿠키로 현재 유저를 인증한다.
  - 닫히지 않았고 활성 room member가 1명 이상인 room 목록, 활성 room member 수, 현재 유저가 active member인지 여부를 반환한다.
  - 현재 유저가 유효한 대기 로비에 이미 참여 중이면 `current_membership`에 room 요약과 `/ws/lobby/rooms/{room_public_id}` 연결 path를 함께 반환한다.
  - 목록 조회는 snapshot이고, 특정 room의 실시간 이벤트는 room 참여 후 WebSocket으로 받는다.
- `POST /api/v1/game/rooms`
  - `session_token` 쿠키로 현재 유저를 인증한다.
  - `waiting` 상태 room을 생성하고 방장을 첫 활성 `game.room_members`로 등록한다.
  - 성공 응답의 `room_public_id`로 `/ws/lobby/rooms/{room_public_id}`에 연결할 수 있다.
- `POST /api/v1/game/rooms/{room_public_id}/join`
  - `session_token` 쿠키로 현재 유저를 인증한다.
  - room row를 lock한 뒤 `waiting` 상태와 정원을 확인한다.
  - 참여 정보는 DB의 `game.room_members`에 저장한다.
  - 이미 활성 room member인 유저의 반복 요청은 새 row를 만들지 않고 기존 참여 정보를 반환한다.
  - 신규 멤버가 추가된 경우(`already_member=false`) `/ws/lobby/rooms/{room_public_id}`의 같은 room
    연결에 `lobby.room.joined`를 broadcast한다.
  - 이미 참여 중인 반복 join 요청은 REST 응답만 반환하고 WebSocket event를 보내지 않는다.
- `POST /api/v1/game/rooms/{room_public_id}/leave`
  - `session_token` 쿠키로 현재 유저를 인증한다.
  - `waiting` room row를 lock한 뒤 현재 유저의 활성 `room_members.left_at`을 기록한다.
  - 방장이 나갔고 남은 활성 멤버가 있으면 가장 먼저 입장한 남은 멤버에게 방장을 승계한다.
  - 마지막 멤버가 나가면 room을 `closed`로 바꾸고 `closed_at`을 기록해 목록, 참여, WebSocket 진입에서 제외한다.
  - 성공 후 `/ws/lobby/rooms/{room_public_id}`의 같은 room 연결에 `lobby.room.left`를 broadcast한다.
- `PATCH /api/v1/game/rooms/{room_public_id}`
  - `session_token` 쿠키로 현재 유저를 인증한다.
  - 방장만 `waiting` 상태 room의 이름, 실제 유저 최대 인원, `rule_config`를 수정할 수 있다.
  - `rule_config.max_rounds`는 끝말잇기 판 수이고, `rule_config.turn_time_seconds`는 기본 턴 제한 시간이다.
  - 현재 활성 멤버 수보다 작은 `max_players`로 줄일 수 없다.
  - 성공 후 commit 바깥에서 같은 room 연결에 `lobby.room.updated`를 broadcast한다.
- `POST /api/v1/game/rooms/{room_public_id}/start`
  - `session_token` 쿠키로 현재 유저를 인증한다.
  - 방장만 게임을 시작할 수 있다.
  - 시작 판단 전에 room row를 lock해 같은 room의 동시 start 요청을 직렬화한다.
  - 아직 종료되지 않은 active session이 이미 있으면 새 session을 만들지 않고 기존 `game_session_public_id`와 참가자 snapshot을 반환한다.
  - 응답에는 현재 요청 유저만 사용할 수 있는 `game_session_token`과 만료 시각을 포함한다.
  - room은 `waiting` 상태여야 하고, 방장은 활성 `game.room_members`에 포함되어야 한다.
  - 시작 시 활성 room member를 `game.session_participants`의 실제 유저 참가자로 고정한다.
  - 실제 유저 뒤에 AI 손님 1명을 `participant_type='ai'`, `is_uninvited_guest=true`로 추가한다.
  - public 참가자 payload는 `display_name`, `seat_number`만 포함한다. `display_name`은 `1번 손님`처럼 익명화하고, `participant_type`, `is_uninvited_guest`, 원래 닉네임은 결과 공개 전까지 노출하지 않는다.
  - 시작 시점의 room `rule_config`를 `game_sessions.rule_config`에 snapshot으로 고정한다.
  - 끝말잇기 세션 시작 시 첫 번째 턴 phase와 `word_game.turns` row를 함께 생성하고 `game_sessions.current_phase_id`로 지정한다.
  - `game_sessions.current_phase_id`는 `session_phases.id` FK이므로 시작 transaction은 game session과 participants를 먼저 flush하고, 첫 phase와 turn을 flush한 뒤 마지막에 `current_phase_id`를 갱신한다.
  - 첫 턴은 `round_number=1`, `turn_number=1`, actor는 `seat_number=1`, `required_start_char=null`이다.
  - 응답은 `game_sessions.public_id`인 `game_session_public_id`를 반환한다. 이 값은 한 게임 세션의 공개 식별자이며 라운드 ID가 아니다.
- `GET /api/v1/game/sessions/{game_session_public_id}/entry`
  - `session_token` 쿠키로 현재 유저를 인증한다.
  - 현재 유저가 해당 session의 실제 유저 참가자로 고정되어 있을 때만 `allowed=true`를 반환한다.
  - 시작 시 확정된 참가자가 아닌 유저는 `GAME_SESSION_ENTRY_FORBIDDEN`으로 거부한다.
  - 허용된 유저에게는 `game_session_token`을 새로 발급해 이후 match 재연결에 사용할 수 있게 한다.

이 REST gate는 `/ws/realtime`과 무관하다. `/ws/realtime`은 계속 ping/pong 연결 테스트용이고,
`/ws/lobby/rooms/{room_public_id}`는 연결 시점에 `session_token`으로 유저 세션을 확인한 뒤 path의
room에 대한 활성 member 여부를 DB로 확인한다. 별도 subscribe message는 사용하지 않고, path의
room public_id가 연결의 이벤트 범위가 된다. room과 room member의 최종 사실은 DB이며, `/ws/match`는
같은 세션 참가자 권한 기준을 재사용해야 한다.

room 로비 연결은 heartbeat와 grace 퇴장 정책을 가진다. client가 주기적으로 `ping`을 보내고 서버는
마지막 메시지 이후 45초 동안 새 메시지가 없으면 연결을 닫는다. 연결 종료 후 90초 안에 같은 유저가
같은 room으로 재연결하면 퇴장 처리를 취소한다. 복귀하지 않으면 `game.room_members.left_at`을 기록하고
같은 room 연결에 `lobby.room.left`를 broadcast한다.

REST handler 안에서 WebSocket 알림이 필요하면 API response에 WebSocket 객체를 담는 방식이
아니라, 서버 process 안의 lobby connection manager를 호출해 이미 열린 room 연결에 event를
broadcast한다. 단일 서버에서는 `room_public_id -> websocket` registry에 직접
`game.started`를 보내고, 여러 서버 instance에서는 Redis Pub/Sub, PostgreSQL NOTIFY, outbox 같은
event bus를 통해 각 instance가 자신이 가진 연결에 broadcast한다.

room 로비 화면의 초기 멤버 리스트는 `/ws/lobby/rooms/{room_public_id}` 연결 성공 직후 서버가 보내는
`lobby.room.snapshot`으로 초기화한다. Snapshot은 활성 멤버를 `joined_at` 순서로 담고, 이후 입장/퇴장
변경분은 `lobby.room.joined`, `lobby.room.left` event로 반영한다.

`/ws/match` 연결은 연결 시점에 유효한 `session_token + game_session_public_id` 조합 또는
`game_session_token`으로 participant identity를 복원한다. 연결이 성립하면 내부 connection identity를
`game_session_id + participant_id + user_id`로 고정한다. 연결이 성립한 뒤 match 진행 command는
로그인 세션이 아니라 participant identity 기준으로 처리한다. 로그인 세션 만료는 진행 중 match를
즉시 끊는 기준으로 쓰지 않고, 새 lobby 연결, 새 게임 시작 같은 새 계정 권한 행위에서만 다시 검증한다.

게임 시작과 게임 세션 진입 확인은 로그인 `session_token`과 별개로 현재 실제 유저 참가자에게만
`game_session_token`을 발급한다. `game_session_public_id`는 `game.game_sessions.public_id` 공개 식별자이고
비밀 토큰이 아니다. `game_session_token`은 `game.session_participants`의 실제 유저 참가자 row에
hash와 만료 시각으로 저장하는 match 복구 credential이다. `/ws/match`는 초기 연결 시 유효한 로그인
세션과 `game_session_public_id` 조합을 사용할 수 있고, 로그인 세션이 만료되었거나 재연결 중이면
`game_session_token` hash로 participant identity를 복원할 수 있다. 방 전체에 같은 `game.started`
payload를 broadcast할 때는 토큰을 넣지 말고, 토큰은 현재 유저에게만 돌아가는 REST response 또는
사용자별 handoff payload에만 포함한다.

## Room and Session State

권장 상태 흐름은 다음과 같다.

```text
lobby
  -> room_waiting
  -> game_starting
  -> round_playing
  -> turn_active
  -> round_finished
  -> voting
  -> result
  -> room_waiting
```

- `room_waiting`: 참가자 정보 확인, 대기, 설정 수정, 나가기, 게임 시작을 처리한다. 준비 상태와 채팅은 확장 후보이다.
- `game_starting`: 참가자를 고정하고 AI 손님을 추가하며 가면 표시명을 만든다.
- `round_playing`: 현재 라운드의 턴 순서를 진행한다.
- `turn_active`: 서버 timer 기준으로 현재 Guest의 입력 제한 시간을 관리한다.
- `round_finished`: 다음 라운드 이동 또는 최종 투표 이동을 결정한다.
- `voting`: 플레이어 투표를 수집한다.
- `result`: 단어 게임 점수와 투표 점수를 합산해 등수와 우승자를 계산한다.

## Game Types

현재 Agent는 `shiritori`, `chosung`, `contains`를 지원한다. 캡처의 상세 규칙은 `shiritori`에 집중되어 있다.

### Shiritori Rules

현재 Backend MVP에서 확정된 끝말잇기 규칙은 다음과 같다.

- 첫 플레이어는 자유롭게 단어를 입력한다.
- 다음 플레이어는 이전 단어의 마지막 글자로 시작하는 단어를 입력한다.
- 이미 사용된 단어는 다시 사용할 수 없다.
- 제한 시간 내 입력하지 못하면 실패 처리된다.
- 플레이어당 기본 입력 시간은 room `rule_config.turn_time_seconds`이며 기본값은 10초다.
- 성공한 단어 제출은 같은 Round 안의 다음 Turn으로 이어진다.
- 단어 실패와 AI 답변 실패는 공개 판정으로 기록하되 현재 턴을 유지한다.
- 제한 시간 초과는 현재 Round를 종료한다.
- 남은 Round가 있으면 다음 Round의 첫 Turn으로 넘어가고, `rule_config.max_rounds`를 채우면 AI 지목 투표로 넘어간다.
- `max_rounds=8`이면 한 게임 세션에서 끝말잇기 8판을 마친 뒤 투표로 넘어간다.

Cycle은 도메인 개념으로 남겨두되, 현재 Backend MVP는 Cycle row를 저장하거나 Cycle 종료마다 시간을 줄이지 않는다.

### Shiritori Score

현재 Backend MVP 점수 규칙은 다음과 같다.

- 단어 제출 성공: `+10`
- 앞글자 미스: `-5`
- 중복 단어 입력: `-1`
- AI를 맞힌 투표자: `+10`
- AI가 아닌 참가자를 지목한 투표자: `-5`
- AI로 지목된 AI 손님: 지목 1건당 `-5`

아래 규칙은 기획 확장 후보이며 현재 Backend MVP 로직에는 아직 들어가지 않았다.

- 5초 내 입력: `+10`
- 10초 내 입력: `+5`
- 기본 룰에서 4자 이상 단어 입력: `+3`
- 제한 시간 초과: `-10`
- 한 글자 단어 금지
- Cycle 종료마다 입력 시간 1초 감소

## Submission Validation Policy

2026-06-12 frontend 레퍼런스 조사에서 kkutu는 클라이언트가 시작 글자 등 일부 조건을 알 수 있어도
최종 단어 제출을 서버로 보내고, 서버가 단어 인정 여부와 실패/패널티를 authoritative하게 broadcast하는
흐름으로 확인됐다.

해질녘도 단어 입력 검증의 최종 경계를 Backend에 둔다.

- 클라이언트는 입력 가능 턴, 시작 글자, 글자 수 같은 빠른 UX 검증을 할 수 있지만 보안/점수 경계가 아니다.
- `/ws/match`는 클라이언트가 보낸 최종 `Submission`을 받아 서버 상태 기준으로 차례, 제한 시간,
  게임 종류별 조건, 중복 사용, 사전 존재 여부를 검증한다.
- 시작 글자 불일치, 사전 미등재, 중복 단어처럼 실패가 예상되는 입력도 서버까지 도달할 수 있다고 보고
  handler를 설계한다.
- 단어 인정 여부, 점수 변화, 패널티, 추천/대체 단어 후보가 필요하면 서버 event로 내려준다.
- Agent는 후보 단어 제공을 맡고, 실제 사용자 제출의 인정/실패와 점수 반영은 Backend match domain이
  결정한다.

### Expansion Rules

- 글자 수 고정: 2자, 3자, 4자 이상
- 폭탄 돌리기: 정해진 시간이 끝날 때 차례인 플레이어 `-10`
- 라운드별 미션

## Voting Rules

- 모든 게임이 종료된 후 플레이어 투표를 진행한다.
- 투표 시간은 20초 기준이다.
- 플레이어는 AI로 의심되는 Guest를 공개 순서 번호로 지목한다. client는 participant UUID를 알 필요가 없다.
- AI를 찾아낸 경우 투표한 플레이어는 `+10`을 얻는다.
- 다른 플레이어를 지목한 경우 투표한 플레이어는 지목 1건당 `-5`를 받는다.
- AI로 지목된 경우 AI Guest는 투표 수당 `-5`를 받는다.
- 동률이면 공동 표시한다.
- 투표 결과를 포함한 최종 점수로 플레이어 등수를 표시한다.
- 투표 진행 중에는 다른 참가자의 target을 broadcast하지 않고, 모든 실제 유저 투표 완료 후 결과 event에서
  `revealed_participant_type`으로 AI 여부를 공개한다.

## WebSocket Message Areas

구현 시 구체적인 message type은 `/ws/lobby/rooms/{room_public_id}`, `/ws/match` 계약 문서와 함께 확정한다.

실시간 관심사는 처음부터 물리 endpoint를 분리해 설계한다.

- `/ws/lobby/rooms/{room_public_id}`: 참여가 허용된 객실의 대기방 snapshot, 입장/퇴장, 설정 변경, 시작 handoff
- `/ws/match`: 실제 게임 세션, 라운드, 턴, 입력, 점수, 투표, 결과
- `/ws/realtime`: ping/pong 연결 테스트용. 게임 상태를 다루지 않는다.

현재 `/ws/lobby/rooms/{room_public_id}` client command:

- `ping`

로비 확장 command 후보:

- room 나가기
- room 준비 상태 변경
- room 채팅 전송
- quick start 요청/취소
- game 시작 요청

현재 `/ws/lobby/rooms/{room_public_id}` server event:

- `lobby.room.connected`
- `lobby.room.snapshot`
- `lobby.room.joined`
- `lobby.room.left`
- `lobby.room.updated`
- `game.started`
- `lobby.pong`

로비 확장 event 후보:

- lobby room list snapshot/update
- quick start status/match queue/countdown update
- ready state changed
- chat message

현재 `/ws/match` client command:

- `ping`
- `word.submit`
- `vote.submit`

현재 `/ws/match` server event:

- `match.connected`
- match snapshot
- submission accepted/rejected
- turn timeout/failed
- vote accepted/timeout
- result published

`/ws/match` 확장 event 후보:

- round started/finished
- turn started
- timer tick
- score updated
- invalid submission with optional candidate hints
- voting started/finished
- match 나가기 또는 포기

순서가 중요한 메시지는 `sequence`를 둔다. client 명령 재시도나 응답 매칭이 필요한 메시지는 `request_id`를 둔다.
client command에 대한 일회성 응답과 다수 client가 받는 broadcast event는 handler를 분리한다.

빠른 시작은 다음 UI 상태 머신으로 다룬다.

```text
idle -> matching -> settled -> countdown -> transitioning -> playing
```

- `matching`: 상대 또는 참가자를 찾는 중이며 취소 가능하다.
- `settled`: 매칭이 성사되어 곧 시작한다.
- `countdown`: 경기 시작 전 짧은 카운트다운을 표시한다.
- `transitioning`: 리소스 준비와 scene 전환을 처리한다.
- `playing`: `/ws/match` 상태를 렌더링한다.

## State Management Notes

- 서버 timer를 기준으로 timeout을 판정한다. 클라이언트 timer는 표시용이다.
- `/ws/match` snapshot의 `current_turn.phase_id`는 client가 단어 제출 시 `word.submit.phase_id`로
  되돌려 보내는 현재 턴 식별자다.
- `/ws/match` loop는 heartbeat 대기 시간과 현재 턴 또는 투표 deadline 중 더 이른 시점까지만 client
  frame을 기다리고, deadline이 먼저 도달하면 서버 기준 timeout 확정을 시도한다.
- timeout이 확정된 턴은 `turn_timeout` action/event와 `session_phases.result_status=timeout`으로 저장하고,
  commit 이후 `/ws/match` 연결에 `match.turn.resolved`를 `payload.result=timeout`으로 보낸다.
- deadline 이후 도착한 `word.submit`도 연결 오류로 닫지 않고 같은 timeout 확정 경로로 처리한다.
- Timeout으로 현재 끝말잇기 한판이 종료되면 남은 판이 있을 때 `next_turn`, 모든 판이 끝났을 때
  `next_status=voting`과 `voting_deadline_at`을 함께 보내 화면 전환을 동기화한다.
- reconnect가 필요하므로 room/session snapshot을 재전송할 수 있어야 한다.
- disconnect cleanup은 room membership과 game session 정책을 분리해 다룬다.
- AI answer 요청은 Backend가 현재 GameSession 상태를 검증한 뒤 Agent에 보낸다.
- Agent answer 요청에는 해당 game session의 `used_words`와 현재 턴의 `required_start_char`를
  `last_char`, `condition.last_char`로 함께 보낸다.
- Agent가 `no_candidate`를 반환하면 Backend가 AI 손님의 실패/감점 또는 대체 정책을 결정한다.
- Agent API timeout, 네트워크 오류, 4xx/5xx, invalid payload처럼 답변이 돌아오지 않는 경우도 Backend가
  `ai_answer_failed` action/event로 확정하고, commit 이후 `/ws/match` 연결에 `match.turn.resolved`를
  `payload.result=failed`로 보낸다.
- AI 실패는 현재 phase를 종료하거나 다음 턴/투표로 전환하지 않는다. 현재 턴은 deadline까지 유지하고,
  실제 턴 종료와 다음 판/투표 전환은 `turn_timeout` 확정 경로만 담당한다.
- Agent 호출 대기 중 서버 timeout 등으로 phase가 이미 종료된 경우, 뒤늦게 도착한 AI 성공/실패는 추가 event 없이
  무시한다.
- AI 성공 답변이 도착했더라도 서버 deadline이 이미 지났으면 단어 제출로 저장하지 않고 `turn_timeout`으로
  확정한다.
- 사용자가 `/ws/match`에 `word.submit`을 보내면 Backend가 현재 턴 actor, deadline, 시작 글자, 사전 등재,
  중복 단어를 검증한 뒤 제출/사용 단어/점수/다음 턴을 저장하고 commit 이후 `match.turn.resolved`를
  `payload.result=accepted`로 보낸다.
- 시작 글자 불일치, 사전 미등재, 중복 단어처럼 게임 규칙상 거절된 단어 제출은 연결 오류로 처리하지 않는다. Backend는
  `word_reject` action, score ledger, `word.rejected` event를 저장하고 commit 이후 `match.turn.resolved`를
  `payload.result=rejected`로 broadcast하며 현재 턴은 유지한다. 제출이 있는 `accepted`/`rejected` 판정은
  정답 여부와 무관하게 `word`, `normalized_word`를 모든 연결 client에 공개한다.
- 다음 턴이 AI actor이고 Agent answer 설정이 활성화되어 있으면 Backend가 바로 AI 턴을 실행해 추가
  `match.turn.resolved` event를 같은 세션에 broadcast한다.
- `voting` 상태에서 `/ws/match`의 `vote.submit`은 `target_seat_number`만 받는다. 투표 저장 후
  `match.vote.accepted`를 보내고, 모든 실제 유저가 투표하면 `SessionResult`와 투표 점수 ledger를 저장한
  뒤 `match.result.published`를 같은 세션에 broadcast한다.
- 투표 전환 시 `phase_type=voting` phase와 `voting_deadline_at`을 저장해 snapshot과 서버 timer가 복구할
  수 있게 한다. Deadline까지 투표하지 않은 실제 유저는 투표 점수 0점으로 남기고, 제출된 투표만 반영해
  `match.vote.timeout`과 `match.result.published`를 broadcast한다.
- deadline 이후 도착한 `vote.submit`도 저장하지 않고 같은 투표 timeout 확정 경로로 처리한다.
- 여러 match 연결이 같은 투표 deadline을 감지할 수 있으므로 이미 `result` 상태가 된 세션의 stale timeout은
  추가 event 없이 무시한다.
- 결과 확정 이후 재접속한 참가자는 `match.snapshot.results`로 `SessionResult` 기반 최종 점수, 순위, 우승
  여부, 공개 participant type, vote score delta를 복구한다.
- 점수 계산은 누적 total이 아니라 ScoreLedger event 합산으로 설명 가능해야 한다.
- 로비/객실/매치 snapshot은 재접속과 화면 복구의 기준 데이터가 되어야 한다.
- command-response 패턴은 `request_id`로 매칭하고, broadcast는 `sequence`로 순서를 관리한다.
- 단어 게임 화면에는 현재 조건, 남은 턴 시간, 단어 기록, 점수판, 미션 진행도, 사전 뜻을 분리된 상태로 둔다.
- 상대 차례에도 예측 입력이나 다음 단어 준비 UX를 제공하면 대기 시간이 줄어든다.
- 연결 상태, ping, 버전 정보는 운영 디버깅과 사용자 신뢰를 위해 표시할 수 있다.

## Reference Service Takeaways

`kkutu.kr` 분석 문서에서 가져올 수 있는 참고점은 다음과 같다.

- 로그인 전 게스트 플레이를 허용하면 진입 장벽을 낮출 수 있다. 다만 현재 해질녘은 계정 기반 로그인을 먼저 정의했으므로 게스트 모드는 별도 결정이 필요하다.
- 첫 화면의 가장 강한 CTA는 빠른 시작이어야 한다. 방 목록 탐색은 보조 흐름으로 둘 수 있다.
- 로비는 방 목록만이 아니라 공지, 채팅, 친구/접속자, 빠른 시작, 커뮤니티 링크를 포함하는 허브로 볼 수 있다.
- 빠른 시작은 대기, 취소, 매칭 성사, 카운트다운, 경기 전환을 명시적 상태로 나눠야 한다.
- 실시간 게임은 REST보다 WebSocket event 중심으로 설계하고, REST는 계정, 설정, 낱말집, 검색 같은 보조 기능에 둔다.
- 경기 화면은 현재 턴 판단에 필요한 정보인 조건, 타이머, 입력창, 단어 기록, 점수, 미션, 사전 정보를 한 화면에 밀도 있게 제공한다.
- scene 전환은 URL 이동보다 같은 play 화면 안의 상태 전환으로 시작하는 것이 자연스럽다.

Source: [`kkutu-analysis.md`](https://github.com/haejillyeok/frontend/blob/dev/docs/kkutu-analysis.md)

## Open Questions

- 객실 최대 실제 플레이어 수와 AI 포함 총 참가자 수의 기준
- 게임 시작 권한: 방장 수동 시작인지, 전원 준비 자동 시작인지
- 게임 시작 시 AI 손님 수 결정 방식
- Cycle 기반 종료 조건이나 입력 시간 감소를 MVP 이후 도입할지
- 입력 실패 후 제한 시간 내 재입력 허용 여부
- 동점 처리: 공동 우승만 표시할지, 타이브레이커를 둘지
- 결과 공개 시점에 AI 정체와 원래 닉네임을 언제 공개할지
- 로그인 전 게스트 플레이를 허용할지, 로그인 필수 게임으로 유지할지
- 매치 중에도 `/ws/lobby/rooms/{room_public_id}` 연결을 유지할지, `/ws/match`만 유지하고 종료 후 재연결할지
- AI Guest도 최종 우승자가 될 수 있는지, 플레이어가 AI를 찾지 못했을 때 AI에게 보상을 줄지
- 5초 내 입력 점수와 10초 내 입력 점수가 배타적 구간인지 누적 보너스인지

## Related

- [realtime-websocket.md](realtime-websocket.md)
- [decisions/2026-06-11-split-lobby-match-websockets.md](decisions/2026-06-11-split-lobby-match-websockets.md)
- [decisions/2026-06-05-users-table-poc.md](decisions/2026-06-05-users-table-poc.md)
- [decisions/2026-06-11-agent-qdrant-mvp.md](decisions/2026-06-11-agent-qdrant-mvp.md)
