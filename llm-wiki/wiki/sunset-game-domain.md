---
title: Sunset Game Domain
type: domain-model
updated: 2026-06-11
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
- 실제 게임 실시간 통신은 처음부터 BE `/ws/lobby`, `/ws/match` WebSocket으로 분리한다.
- 클라이언트는 서버 snapshot/event를 렌더링하고, 게임 상태의 최종 사실은 Backend가 가진다.
- Agent는 AI 손님의 단어 후보를 제공한다. 방, 턴, 라운드, 점수, 투표, 승패 계산은 Backend 책임이다.
- 게임 시작 시 AI 플레이어가 `Uninvited Guest`로 추가된다. 대기방에서 AI를 미리 포함시킬 필요는 없다.
- 게임 시작 후 닉네임은 가면 처리된 표시명으로 가려질 수 있다.

## Core Concepts

- `User`: 로그인 가능한 계정. 기존 users 도메인의 account_id, password, nickname 기준을 따른다.
- `Guest`: 객실 안의 참가자 단위. 실제 User 또는 AI 손님일 수 있다.
- `Uninvited Guest`: AI Guest. 플레이어는 게임 후 투표로 이 Guest를 찾아낸다.
- `Lobby`: 객실 목록, 객실 만들기, 객실 찾기, 빠른 입장, 친구 손님 리스트, 게임 종류 필터를 제공하는 공간.
- `Room`: 참가자가 대기하고 게임 세션을 시작하는 객실. 방 ID, 이름, 게임 종류, 참가자, 준비 상태, 상태를 가진다.
- `GameSession`: 한 객실에서 시작되어 결과가 확정될 때까지의 실행 단위. AI 추가, 가면 처리, 라운드, 턴, 사용 단어, 점수, 투표를 포함한다.
- `Round`: 게임 반복 단위. 끝말잇기 기준 최대 8라운드 후 종료된다.
- `Turn`: 특정 Guest가 제한 시간 안에 입력해야 하는 차례. 시작 시각, 제한 시간, 조건, 제출, 성공/실패 결과를 가진다.
- `Submission`: Turn 중 입력된 단어와 검증 결과.
- `ScoreLedger`: 점수 변경 사유별 기록. 최종 점수만 저장하지 않고 사유를 함께 보존한다.
- `Vote`: 게임 종료 후 AI 손님을 지목하는 투표. 투표 시간은 20초 기준이다.

## User Flow

1. 로그인
2. 로비
3. 방 입장
4. 준비
5. 게임 시작과 가면 처리
6. 게임 진행
7. 모든 라운드 종료 후 AI 지목 투표
8. 총점 계산과 우승자 발표

## REST Session Gate

게임 진행 WebSocket을 붙이기 전에는 REST API로 게임 시작과 세션 진입 권한을 먼저 고정한다.

- `POST /api/v1/game/rooms/{room_public_id}/start`
  - `session_token` 쿠키로 현재 유저를 인증한다.
  - 방장만 게임을 시작할 수 있다.
  - 시작 판단 전에 room row를 lock해 같은 room의 동시 start 요청을 직렬화한다.
  - 아직 종료되지 않은 active session이 이미 있으면 새 session을 만들지 않고 기존 `session_public_id`와 참가자 snapshot을 반환한다.
  - room은 `waiting` 상태여야 하고, 방장은 활성 `game.room_members`에 포함되어야 한다.
  - 시작 시 활성 room member를 `game.session_participants`의 실제 유저 참가자로 고정한다.
  - 실제 유저 뒤에 AI 손님 1명을 `participant_type='ai'`, `is_uninvited_guest=true`로 추가한다.
  - 응답은 `game_sessions.public_id`인 `session_public_id`를 반환한다.
- `GET /api/v1/game/sessions/{session_public_id}/entry`
  - `session_token` 쿠키로 현재 유저를 인증한다.
  - 현재 유저가 해당 session의 실제 유저 참가자로 고정되어 있을 때만 `allowed=true`를 반환한다.
  - 시작 시 확정된 참가자가 아닌 유저는 `GAME_SESSION_ENTRY_FORBIDDEN`으로 거부한다.

이 REST gate는 `/ws/realtime`과 무관하다. `/ws/realtime`은 계속 ping/pong 연결 테스트용이고,
이후 `/ws/lobby`, `/ws/match`는 같은 세션 참가자 권한 기준을 재사용해야 한다.

REST handler 안에서 WebSocket 알림이 필요하면 API response에 WebSocket 객체를 담는 방식이
아니라, 서버 process 안의 lobby connection manager를 호출해 이미 열린 room 연결에 event를
broadcast한다. 단일 서버에서는 `room_public_id -> user_id -> websocket` registry에 직접
`game.started`를 보내고, 여러 서버 instance에서는 Redis Pub/Sub, PostgreSQL NOTIFY, outbox 같은
event bus를 통해 각 instance가 자신이 가진 연결에 broadcast한다.

`/ws/match` 연결은 연결 시점에만 `session_token`으로 user_id를 복원하고,
`user_id + session_public_id`로 `game.session_participants`를 조회해 내부 connection identity를
`game_session_id + participant_id + user_id`로 고정한다. 연결이 성립한 뒤 match 진행 command는
로그인 세션이 아니라 participant identity 기준으로 처리한다. 로그인 세션 만료는 진행 중 match를
즉시 끊는 기준으로 쓰지 않고, 새 lobby 연결, 새 match 연결, 새 게임 시작 같은 새 권한 행위에서만
다시 검증한다.

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

- `room_waiting`: 참가자 정보 확인, 준비/대기, 채팅, 나가기를 처리한다.
- `game_starting`: 참가자를 고정하고 AI 손님을 추가하며 가면 표시명을 만든다.
- `round_playing`: 현재 라운드의 턴 순서를 진행한다.
- `turn_active`: 서버 timer 기준으로 현재 Guest의 입력 제한 시간을 관리한다.
- `round_finished`: 다음 라운드 이동 또는 최종 투표 이동을 결정한다.
- `voting`: 플레이어 투표를 수집한다.
- `result`: 단어 게임 점수와 투표 점수를 합산해 등수와 우승자를 계산한다.

## Game Types

현재 Agent는 `shiritori`, `chosung`, `contains`를 지원한다. 캡처의 상세 규칙은 `shiritori`에 집중되어 있다.

### Shiritori Rules

- 첫 플레이어는 자유롭게 단어를 입력한다.
- 다음 플레이어는 이전 단어의 마지막 글자로 시작하는 단어를 입력한다.
- 이미 사용된 단어는 다시 사용할 수 없다.
- 한 글자 단어는 사용할 수 없다.
- 제한 시간 내 입력하지 못하면 실패 처리된다.
- 플레이어당 기본 입력 시간은 10초다.
- 모든 플레이어의 차례가 지나면 입력 시간이 1초씩 줄어든다.
- 최대 8라운드 후 게임은 종료된다.

### Shiritori Score

- 5초 내 입력: `+10`
- 10초 내 입력: `+5`
- 기본 룰에서 4자 이상 단어 입력: `+3`
- 앞글자 미스: `-5`
- 제한 시간 초과: `-10`
- 중복 단어 입력: `-1`

### Expansion Rules

- 글자 수 고정: 2자, 3자, 4자 이상
- 폭탄 돌리기: 정해진 시간이 끝날 때 차례인 플레이어 `-10`
- 라운드별 미션

## Voting Rules

- 모든 게임이 종료된 후 플레이어 투표를 진행한다.
- 투표 시간은 20초 기준이다.
- 플레이어는 AI로 의심되는 Guest를 지목한다.
- AI를 찾아낸 경우 투표한 플레이어는 `+10`을 얻는다.
- 다른 플레이어를 지목한 경우 투표한 플레이어는 지목 1건당 `-5`를 받는다.
- AI로 지목된 경우 AI Guest는 투표 수당 `-5`를 받는다.
- 동률이면 공동 표시한다.
- 투표 결과를 포함한 최종 점수로 플레이어 등수를 표시한다.

## WebSocket Message Areas

구현 시 구체적인 message type은 `/ws/lobby`, `/ws/match` 계약 문서와 함께 확정한다.

실시간 관심사는 처음부터 물리 endpoint를 분리해 설계한다.

- `/ws/lobby`: 로비, 방 목록, 빠른 시작, 방 생성/입장/퇴장, 대기방, 준비 상태, 로비/방 채팅
- `/ws/match`: 실제 게임 세션, 라운드, 턴, 입력, 점수, 투표, 결과
- `/ws/realtime`: ping/pong 연결 테스트용. 게임 상태를 다루지 않는다.

Client command 후보:

- lobby 구독/해제
- room 생성, 입장, 나가기
- room 준비 상태 변경
- room 채팅 전송
- quick start 요청/취소
- game 시작 요청

Server event 후보:

- lobby room list snapshot/update
- quick start status/match queue/countdown update
- room snapshot
- guest joined/left
- ready state changed
- chat message
- game started

`/ws/match` client command 후보:

- match 참가/복구
- turn 단어 제출
- vote 제출
- match 나가기 또는 포기

`/ws/match` server event 후보:

- match snapshot
- round started/finished
- turn started
- timer tick 또는 deadline
- submission accepted/rejected
- score updated
- voting started/finished
- result published

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
- reconnect가 필요하므로 room/session snapshot을 재전송할 수 있어야 한다.
- disconnect cleanup은 room membership과 game session 정책을 분리해 다룬다.
- AI answer 요청은 Backend가 현재 GameSession 상태를 검증한 뒤 Agent에 보낸다.
- Agent가 `no_candidate`를 반환하면 Backend가 AI 손님의 실패/감점 또는 대체 정책을 결정한다.
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
- 입력 실패 후 제한 시간 내 재입력 허용 여부
- 동점 처리: 공동 우승만 표시할지, 타이브레이커를 둘지
- 결과 공개 시점에 AI 정체와 원래 닉네임을 언제 공개할지
- room/session/result를 메모리로만 관리할지 DB에 영속화할지
- 로그인 전 게스트 플레이를 허용할지, 로그인 필수 게임으로 유지할지
- 매치 중에도 `/ws/lobby` 연결을 유지할지, `/ws/match`만 유지하고 종료 후 재연결할지
- AI Guest도 최종 우승자가 될 수 있는지, 플레이어가 AI를 찾지 못했을 때 AI에게 보상을 줄지
- 5초 내 입력 점수와 10초 내 입력 점수가 배타적 구간인지 누적 보너스인지
- 최대 8라운드의 라운드가 전체 참가자 1회전인지, 개별 턴 수인지

## Related

- [realtime-websocket.md](realtime-websocket.md)
- [decisions/2026-06-11-split-lobby-match-websockets.md](decisions/2026-06-11-split-lobby-match-websockets.md)
- [decisions/2026-06-05-users-table-poc.md](decisions/2026-06-05-users-table-poc.md)
- [decisions/2026-06-11-agent-qdrant-mvp.md](decisions/2026-06-11-agent-qdrant-mvp.md)
