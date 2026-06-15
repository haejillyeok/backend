# LLM Wiki Log

이 파일은 `llm-wiki/` 정보 자체의 시간순 변경 이력입니다. 새 항목은 위에 추가합니다.
코드 변경 상세는 Git history, PR, issue에서 확인하고, 이 파일에는 위키 페이지의 지식, 계약, 정책,
컨벤션이 어떻게 바뀌었는지만 남깁니다.

## [2026-06-15] maintenance | Add match server time synchronization contract

- `game.started`, Match `snapshot`/`pong`/진행/라운드/투표/결과 event가 `server_time`을 포함해 client가 서버-로컬 시계 offset을 보정한다는 계약을 정리했다.
- 화면 timer는 `server_time` 기반 offset과 `started_at`/`deadline_at`/`voting_deadline_at`으로 표시하되, 실제 timeout과 결과 확정은 서버 deadline 판정이 권위자라는 기준을 명시했다.
- 테스트 페이지 기준에 `server_time`을 이용한 카운트다운 보정 원칙을 추가했다.

## [2026-06-15] maintenance | Add random round start character contract

- 끝말잇기 각 라운드 첫 턴 `required_start_char`는 활성 `word_game.valid_words.starts_with` 후보 중 무작위로 선택한다는 계약을 추가했다.
- 후보 단어셋이 비어 있을 때만 라운드 첫 턴을 `required_start_char=null`로 시작한다는 fallback 기준을 정리했다.
- start REST 응답, Lobby `game.started`, Match `match.snapshot`/`match.round.started`가 같은 시작글자 조건을 전달한다는 기준을 반영했다.

## [2026-06-15] maintenance | Add audit payload logging rules

- `observability-stack.md`에 HTTP, WebSocket, Agent outbound 감사 로그의 logger, phase, operation, payload 검열 기준을 정리했다.
- `backend-guidelines-summary.md`에 WebSocket 감사 로그와 Agent 요청/응답 payload 로그를 다음 작업 기준으로 추가했다.
- token/password/API key 계열 payload key는 재귀적으로 검열하고, 게임 단어와 Agent answer/status 같은 비밀값이 아닌 도메인 값은 로그에 남긴다는 기준을 명시했다.

## [2026-06-15] maintenance | Add initial game start countdown

- 끝말잇기 세션 시작 직후 첫 턴 `started_at`은 시작 확정 시각보다 5초 뒤이고, `deadline_at`은 그 시각에 `turn_time_seconds`를 더한 값이라는 계약을 추가했다.
- start REST 응답, Lobby `game.started`, Match `match.snapshot`의 `current_turn`이 `started_at`을 포함해 client가 게임 시작 카운트다운을 표시할 수 있다는 기준을 정리했다.
- 테스트 페이지 기준에 첫 턴 시작 전 카운트다운 표시 기준을 추가했다.

## [2026-06-15] maintenance | Hide AI internals from match clients

- `payload.result=failed`의 공개 `reason`은 내부 `agent_error`/`agent_timeout` 대신 `answer_unavailable`로 통일한다는 기준을 추가했다.
- `match.turn.resolved`의 failed 제출 단어는 공개 계약인 `word`, `normalized_word`로만 노출하고, client가 AI 내부 details key에 의존하지 않는다는 기준을 정리했다.
- 테스트 페이지는 답변자가 AI인지 사람인지 구분하지 않고 제출 단어 공개 필드만 표시한다는 기준을 추가했다.
- Agent가 단어를 반환했지만 Backend 검증에서 실패한 경우에는 AI 실패가 아니라 일반 참가자 오답처럼 `payload.result=rejected`로 broadcast한다는 기준을 정리했다.

## [2026-06-15] maintenance | Clarify AI retry and round countdown

- AI 답변 실패 후에도 같은 AI phase deadline timer를 유지해 timeout 전까지 Agent answer API를 다시 호출할 수 있다는 기준을 정리했다.
- 테스트 페이지는 다음 라운드 첫 턴 `started_at` 전까지 별도 라운드 시작 카운트다운을 표시한다는 기준을 추가했다.

## [2026-06-15] maintenance | Add delayed round start handoff

- 끝말잇기 라운드 timeout 후 남은 판의 첫 턴은 `started_at`을 timeout 확정 시각보다 5초 뒤로 잡고, `match.round.started`도 그 시각에 맞춰 broadcast한다는 계약을 정리했다.
- AI가 단어를 반환했지만 Backend 검증에서 실패한 `failed` 이벤트는 `word`, `normalized_word`에 AI 제출 단어를 포함한다는 기준을 추가했다.
- 테스트 페이지는 timeout의 예약 `next_turn`으로 즉시 현재 턴을 바꾸지 않고, `match.round.started`에서 실제 현재 턴을 전환한다는 기준을 반영했다.

## [2026-06-15] maintenance | Rename word chain game type

- 공개 API와 Agent handler 선택에 쓰는 끝말잇기 game type 식별자를 `shiritori`가 아니라 `word_chain`으로 관리한다는 기준을 정리했다.
- 단어 사전 seed와 `word_game.valid_words.game_type`도 `word_chain` 값을 기준으로 관리한다.

## [2026-06-15] maintenance | Include first turn in game started handoff

- `game.started` handoff event와 start REST 응답이 시작 transaction에서 생성한 첫 `current_turn`을 포함한다는 계약을 추가했다.
- client는 match 연결 전에도 첫 차례 참가자, `phase_id`, deadline을 알 수 있고, `/ws/match` snapshot으로 같은 정보를 복구할 수 있음을 정리했다.

## [2026-06-15] maintenance | Align valid word seed payload fields

- Backend 기본 단어 사전 seed는 `scripts/valid_words_seed.sql`이며 `word_game.valid_words`에 DB 적재용 SQL로 반영한다는 기준을 추가했다.
- `word_game.valid_words`가 시작/끝 글자뿐 아니라 `chosung`, `syllables`, `length`, `used_count` metadata를 함께 관리한다는 DB 설계 기준을 정리했다.

## [2026-06-15] maintenance | Scope used words to current round

- 끝말잇기 `used_words` 중복 판정과 Agent context는 game session 전체가 아니라 현재 라운드 기준이라는 계약을 정리했다.
- `word_game.used_words`의 unique 기준을 `(session_id, round_number, normalized_word)`로 갱신했다.
- `/ws/match` snapshot과 `word.submit` 검증 설명에서 `used_words` 범위를 현재 끝말잇기 판으로 명시했다.
- 한 `Room`이 여러 `GameSession` 이력을 가질 수 있고, 결과 확정 후 같은 room이 다시 `waiting`으로 돌아간다는 상태 흐름을 명시했다.

## [2026-06-15] maintenance | Expand lobby move cleanup policy

- `sunset-game-domain.md`에 새 객실 생성/다른 객실 입장 전 기존 active room membership을 정리한다는 기준을 `waiting` room 밖으로 확장했다.
- 기존 room이 이미 시작됐고 실제 유저가 현재 유저 1명뿐이면 active game session을 `aborted`로 마감하고 room을 `closed`로 닫는 기준을 추가했다.
- 종료 세션은 entry token 발급과 `game_session_token` 복구 대상에서 제외한다는 기준을 추가했다.

## [2026-06-14] maintenance | Clarify single active waiting room membership

- `sunset-game-domain.md`와 `realtime-websocket.md`에 한 유저는 하나의 `waiting` room에만 active member로 남는다는 불변식을 추가했다.
- 객실 생성/다른 객실 입장 전 기존 active waiting membership을 REST 퇴장 규칙으로 정리하고, 정원 초과 입장 실패 시 기존 membership은 유지한다는 기준을 정리했다.

## [2026-06-14] maintenance | Switch WebSocket APM latency to message duration

- `observability-stack.md`에 WebSocket APM latency 판단 기준을 연결 지속 시간이 아니라 유효한 inbound message 처리 시간으로 정리했다.
- `websocket.message.duration` histogram을 endpoint와 message type별 p95/p99 latency 기준으로 사용하고, `websocket.connection.duration`은 연결 수명 관찰용으로 구분한다는 기준을 추가했다.

## [2026-06-14] maintenance | Clarify test page match event state policy

- `test-page-harness.md`에 Match WebSocket `match.turn.resolved` event를 원본 로그뿐 아니라 게임 진행 화면 상태에도 반영한다는 기준을 추가했다.
- 단어 제출 `accepted`/`rejected`/`failed`/`timeout` 판정별 화면 상태와 사용자 notice 갱신 기준을 정리했다.
- 사용자-facing Match WebSocket event는 `match.feed`로 정규화해 최근 판정 카드와 최근 흐름 UI에 표시하고, 내 답변과 다른 손님의 답변을 구분한다는 기준을 추가했다.
- timeout으로 라운드 종료가 확정되면 `match.turn.resolved` 뒤에 `match.round.finished`를 이어서 broadcast하고, 테스트 페이지는 이를 라운드 종료 피드로 표시한다는 기준을 추가했다.
- 다음 라운드 첫 턴이 생성되면 `match.round.started`를 이어서 broadcast하고, 테스트 페이지는 이를 라운드 시작 피드로 표시한다는 기준을 추가했다.

## [2026-06-14] maintenance | Clarify match progress FK write order

- `sunset-game-domain.md`와 `sunset-game-database-design.md`에 단어 제출 성공/거절 저장 시 `participant_actions`, `word_game.submissions`, `session_phases`, `game_events` 사이의 FK 참조 순서에 맞춰 staged insert/flush를 수행한다는 기준을 추가했다.
- timeout으로 다음 판 또는 투표 phase를 만들 때도 새 `session_phases` row를 먼저 확정한 뒤 `game_sessions.current_phase_id`를 갱신한다는 기준을 함께 명시했다.

## [2026-06-14] maintenance | Add OTel route lookup fallback policy

- `observability-stack.md`에 FastAPI/Starlette/OTel route detail 조회가 router 중간 객체에서 실패해도 실제 요청은 500으로 만들지 않고 request path로 fallback한다는 운영 기준을 추가했다.

## [2026-06-14] maintenance | Clarify initial phase FK insert order

- `sunset-game-domain.md`와 `sunset-game-database-design.md`에 `game_sessions.current_phase_id` FK와 `session_phases.session_id` FK의 원형 참조를 고려해 세션 시작 transaction의 staged flush 순서를 명시했다.
- 끝말잇기 첫 phase와 `word_game.turns`는 game session/participants insert 이후 만들고, `current_phase_id`는 phase insert 이후 갱신한다는 현재 DB 쓰기 기준을 정리했다.

## [2026-06-14] maintenance | Clarify session auth error messages

- `2026-06-05-auth-session-login.md`에 `SESSION_EXPIRED` 코드는 유지하되 세션 쿠키가 없을 때는 `로그인이 필요합니다.`, 쿠키가 있지만 활성 세션이 아닐 때는 `세션이 만료되었습니다.` 메시지를 반환한다는 기준을 추가했다.
- `docs/api.md`의 error code 표에도 같은 message 분기 기준을 반영했다.

## [2026-06-14] maintenance | Switch test page port to 3000

- `test-page/` 기본 dev/preview port 기준을 `http://localhost:3000`으로 변경했다.
- BE CORS allowlist 기준에서 repo-local 테스트 페이지 origin을 `http://localhost:3000`으로 통일하고, 이전 테스트 페이지 포트는 더 이상 허용 origin으로 남기지 않는다.
- 운영 API를 로컬 테스트 페이지에서 호출할 때 `session_token`이 브라우저에 저장/전송되도록 prod 쿠키 정책은 `SameSite=None; Secure`, local/dev는 `SameSite=Lax`로 분리한다.

## [2026-06-14] maintenance | Clarify lobby room list visibility

- `sunset-game-domain.md`, `realtime-websocket.md`, `sunset-game-database-design.md`에 로비 목록은 닫히지 않았고 활성 멤버가 1명 이상인 객실만 노출한다는 기준을 명시했다.
- public API 설명도 같은 기준으로 맞춰 0명 객실이 목록에 보이지 않아야 한다는 계약을 정리했다.

## [2026-06-14] maintenance | Add test page harness knowledge

- `test-page/`를 현재 BE/Agent REST와 WebSocket 기능 확인용 정적 harness로 기록했다.
- 테스트 페이지 기본 origin과 BE CORS allowlist 기준을 함께 관리한다는 원칙을 정리했다.
- 이후 테스트 페이지 기준을 BE-only 연결과 체크인 → 로비 → 객실 → 게임 진행 페이지 흐름으로 정정했다.
- 이후 구현을 React/Vite로 전환하고, 요청 URL은 Vite 환경변수, 앱 상태는 `useReducer` store 기준으로 관리한다는 기준을 추가했다.
- 보호 REST API 요청은 JS가 HttpOnly `session_token`을 직접 읽지 않고 `credentials: "include"`로 쿠키를 포함하며, 숨김 운영 노트에서 protected API 세션 확인을 제공한다는 기준을 추가했다.
- 게임 진행 화면은 match snapshot의 server time과 deadline으로 표시용 타이머를 계산하고, participant `is_me`와 actor seat 비교로 내 턴 UI를 강조한다는 기준을 추가했다.
- 기본 UI는 사용자-facing 게임 플로우로 유지하고, 서버 선택/health/문서/원본 로그/Realtime ping은 숨김 운영 노트로 분리한다는 기준을 추가했다.

## [2026-06-14] maintenance | Clarify WebSocket error code contract

- `/ws-docs`의 WebSocket error/close code 표는 lobby, realtime, match 공개 경로 기준으로 6개 코드를 노출한다는 기준을 정리했다.
- match 연결 실패 코드인 `GAME_SESSION_ENTRY_FORBIDDEN`도 WebSocket 문서의 공개 오류 코드에 포함해야 한다는 기준을 추가했다.

## [2026-06-14] maintenance | Add valid word dictionary contract

- 단어 제출과 AI answer는 `word_game.valid_words`의 active 단어셋을 기준으로 유효성을 판정하고, 사전 미등재 단어는 `word_not_in_dictionary` 거절로 broadcast한다는 기준을 추가했다.
- AI answer timeout/error/no_candidate는 현재 턴을 즉시 종료하지 않고 실패 event만 기록하며, 실제 다음 턴/투표 전환은 서버 deadline timeout 확정 경로만 담당한다는 기준을 정리했다.

## [2026-06-14] maintenance | Add game database index strategy

- 로비 목록, 활성 room member 목록, active game session 조회, 점수판 집계, match 재접속 token 조회에 맞춘 현재 게임 DB index 전략을 `sunset-game-database-design.md`에 추가했다.
- 복합 unique constraint가 prefix 조회를 커버하는 경우 같은 첫 column만 가진 단일 index를 별도로 두지 않는다는 기준을 정리했다.

## [2026-06-14] maintenance | Unify match turn result event contract

- `/ws/match`의 단어 성공, 단어 거절, 턴 timeout, AI 답변 실패 public broadcast를 `match.turn.resolved` 하나로 통합하고, 판정 차이는 `payload.result`의 `accepted`, `rejected`, `timeout`, `failed` 값으로 구분한다는 기준을 반영했다.
- 제출이 있는 `accepted`/`rejected` 판정은 정답 여부와 무관하게 `word`, `normalized_word`를 같은 게임 세션의 모든 연결 client에 공개한다는 계약을 정리했다.
- `/ws-docs`는 전체 가로 폭을 사용하고 큰 섹션을 접고 펼칠 수 있으며, 게임 진행과 판정 동기화 Mermaid 흐름을 포함한다는 문서 운영 기준을 추가했다.

## [2026-06-13] maintenance | Align current match MVP docs with implementation

- 끝말잇기 현재 Backend MVP 규칙을 단어 성공/거절, 실패/timeout 라운드 종료, 투표 점수 기준으로 정리하고, Cycle 시간 감소와 시간/길이 보너스는 확장 후보로 분리했다.
- `/ws/match` 현재 client command에 `vote.submit`을 포함하도록 WebSocket 계약 지식을 정정했다.
- 로비 준비 상태, 채팅, 빠른 시작, 결과 후 대기방 복귀는 현재 public API/로직이 아니라 확장 후보라는 기준으로 도메인 설명을 정리했다.
- 로비/매치 WebSocket 분리 결정 문서의 로비 범위를 현재 구현된 설정 변경/start handoff와 확장 후보인 준비/채팅으로 구분했다.
- 서버 간 Agent HTTP client가 `app/shared/clients/agent.py`에 자리잡았다는 현재 상태 기준을 반영했다.

## [2026-06-13] maintenance | Add late AI answer timeout contract

- AI가 성공 답변을 가져왔더라도 서버 deadline이 이미 지난 경우 단어 제출로 저장하지 않고 `turn_timeout` 확정 경로로 처리한다는 기준을 추가했다.

## [2026-06-13] maintenance | Add stale AI turn idempotency contract

- Agent 호출 대기 중 서버 timeout 등으로 phase가 이미 종료된 경우, 뒤늦게 도착한 AI 성공/실패는 추가 action/event 없이 무시한다는 기준을 추가했다.

## [2026-06-13] maintenance | Add stale vote timeout idempotency contract

- 여러 match 연결이 같은 voting deadline을 감지할 수 있으므로, 이미 `result` 상태가 된 세션의 stale vote timeout 시도는 추가 event 없이 무시한다는 기준을 추가했다.

## [2026-06-13] maintenance | Clarify late vote submit timeout contract

- 투표 deadline 이후 도착한 `vote.submit`은 저장하지 않고 WebSocket 연결 오류도 내지 않으며, `match.vote.timeout`과 `match.result.published`로 동기화한다는 기준을 추가했다.
- 투표 timeout은 서버 `voting_deadline_at`과 DB voting phase deadline을 기준으로 확정한다는 계약을 기록했다.

## [2026-06-13] maintenance | Clarify late word submit timeout contract

- 현재 턴 deadline 이후 도착한 `word.submit`은 WebSocket 연결 오류가 아니라 서버 timeout 확정 경로로 처리해 `match.turn.timeout`을 broadcast한다는 기준을 추가했다.
- timeout 판정 이후에도 연결을 유지하고, 다음 상태 동기화는 timeout event payload와 snapshot으로 복구한다는 계약을 기록했다.

## [2026-06-13] maintenance | Add match result snapshot contract

- 결과 확정 이후 재접속한 client가 `match.snapshot.results`로 `SessionResult` 기반 최종 결과를 복구한다는 계약을 추가했다.
- snapshot 결과 항목은 익명 참가자 정보, 공개 participant type, 최종 점수, 순위, 우승 여부, vote score delta, `is_me`를 포함한다는 기준을 기록했다.

## [2026-06-13] maintenance | Add match word rejection event contract

- 시작 글자 불일치와 중복 단어 같은 게임 규칙상 단어 제출 거절은 WebSocket 연결 오류가 아니라 `match.word.rejected` broadcast로 동기화한다는 계약을 추가했다.
- 단어 거절은 `word_reject` action, score ledger, `word.rejected` event로 저장하고 현재 턴을 유지한다는 기준을 기록했다.

## [2026-06-13] maintenance | Add voting deadline timeout contract

- 끝말잇기 마지막 판 종료 후 `phase_type=voting` phase를 만들고 `voting_deadline_at`을 snapshot/event로 복구한다는 기준을 추가했다.
- `/ws/match` loop가 투표 deadline을 서버 기준으로 감지해 `match.vote.timeout`과 `match.result.published`를 broadcast하고, 미투표자는 투표 점수 0점으로 남긴다는 계약을 기록했다.

## [2026-06-13] maintenance | Add match voting and result event contract

- `voting` 상태의 `/ws/match` command를 `vote.submit`으로 정리하고, 익명성을 위해 target participant UUID가 아니라 `target_seat_number`를 받는 기준을 추가했다.
- 투표 저장 후 `match.vote.accepted`는 target을 숨기고 제출 현황만 broadcast하며, 모든 실제 유저 투표 완료 후 `match.result.published`에서 `revealed_participant_type`을 공개한다는 계약을 기록했다.

## [2026-06-13] maintenance | Add match snapshot phase id and timeout wait contract

- `/ws/match` snapshot의 `current_turn.phase_id`를 client가 `word.submit.phase_id`로 되돌려 보내는 현재 턴 식별자로 명시했다.
- `/ws/match` loop가 heartbeat 대기 시간과 현재 턴 deadline 중 더 이른 시점까지만 기다리고, deadline 도달 시 서버 기준 timeout 확정을 시도한다는 기준을 추가했다.

## [2026-06-13] maintenance | Add round-end transition payload contract

- `match.turn.timeout`과 `match.turn.failed`가 끝말잇기 한판 종료를 확정할 때 남은 판이면 `next_turn`, 모든 판이 끝났으면 `next_status=voting`을 함께 보낸다는 계약을 추가했다.
- Agent API timeout, 네트워크 오류, invalid payload처럼 답변이 돌아오지 않는 경우도 Backend가 AI 실패 event로 확정하고 같은 전환 규칙을 적용한다는 기준을 명확히 했다.

## [2026-06-13] maintenance | Add automatic AI turn trigger contract

- `/ws/match`의 사용자 `word.submit` 성공 후 다음 phase가 AI actor이면 Agent answer 설정이 있을 때 AI 턴을 이어서 실행한다는 기준을 추가했다.
- Agent 설정이 없더라도 match 연결과 사용자 제출은 계속 동작하고, AI 자동 실행만 비활성화한다는 운영 기준을 남겼다.

## [2026-06-13] maintenance | Add AI turn Agent answer flow contract

- AI 턴은 DB에서 현재 AI actor, 사용 단어, 시작 글자를 조회한 뒤 Agent answer API를 호출한다는 기준을 추가했다.
- Agent 응답 성공은 기존 단어 제출 확정 경로로, `no_candidate`와 Agent client 오류는 기존 AI 실패 확정 경로로 처리한다는 계약을 정리했다.

## [2026-06-13] maintenance | Add word submit progress event contract

- `/ws/match`의 `word.submit` command와 `match.word.accepted` broadcast 계약을 추가했다.
- 단어 제출 성공 시 제출 action, submission, used word, score ledger, accepted event, 다음 turn phase를 저장하고 commit 이후 broadcast한다는 기준을 정리했다.

## [2026-06-13] maintenance | Add server turn timeout event contract

- 턴 시간 초과는 클라이언트 타이머가 아니라 서버 `deadline_at` 기준으로 확정한다는 기준을 명확히 했다.
- timeout 확정 시 `turn_timeout` action/event를 저장하고 commit 이후 `/ws/match`에 `match.turn.timeout`을 broadcast한다는 계약을 추가했다.

## [2026-06-13] maintenance | Add initial match turn snapshot contract

- 끝말잇기 게임 시작 transaction에서 첫 번째 턴 phase와 `word_game.turns` row를 생성하고 `game_sessions.current_phase_id`로 연결한다는 기준을 추가했다.
- `/ws/match` snapshot은 current phase를 기반으로 `current_turn`을 복구하고, 첫 턴은 `required_start_char=null`이라는 계약을 정리했다.

## [2026-06-13] maintenance | Add match turn failure event contract

- `/ws/match` 연결, snapshot, ping, `match.turn.failed` 기준을 WebSocket 계약 지식에 추가했다.
- Agent 단어 응답 timeout, 오류, `no_candidate`는 Backend가 `ai_answer_failed` action/event로 확정하고 commit 이후 broadcast한다는 기준을 남겼다.

## [2026-06-13] maintenance | Add room settings and anonymous start payload contract

- 방장이 `PATCH /api/v1/game/rooms/{room_public_id}`로 대기 객실 설정을 수정하고 `lobby.room.updated`로 동기화한다는 계약을 추가했다.
- 게임 시작 시 room `rule_config`를 `game_sessions.rule_config`로 snapshot 고정한다는 기준을 정리했다.
- 게임 시작과 세션 진입 public participant payload는 `display_name`, `seat_number`만 포함하고 AI 여부와 원래 닉네임은 숨긴다는 익명화 기준을 반영했다.

## [2026-06-13] maintenance | Clarify shiritori round and cycle terms

- `sunset-game-domain.md`에서 Round를 끝말잇기 한판으로 고정하고, 모든 참가자가 한 번씩 턴을 가진 한 바퀴는 Cycle로 분리했다.
- `max_rounds=8`은 전체 참가자 1회전 수가 아니라 끝말잇기 판 수라는 기준을 정리했다.
- `sunset-game-database-design.md`의 `word_game.turns.round_number`와 `turn_number` 설명에 Round와 Cycle 구분을 반영했다.

## [2026-06-13] maintenance | Clarify auth access IP record semantics

- `2026-06-05-auth-session-login.md`에 `last_access_ip`는 보안 판정용 식별자가 아니라 best-effort 접속 기록이라는 기준을 추가했다.
- 로그인과 회원가입에서는 `Forwarded`, `X-Forwarded-For`, `X-Real-IP`, ASGI peer 순서로 유효한 IP를 기록한다는 현재 계약을 정리했다.

## [2026-06-13] ingest | Add server-authoritative submission validation policy

- frontend `d573890`의 kkutu 입력 검증 분석에서 가져온 단어 제출 검증 경계를 `sunset-game-domain.md`에 반영했다.
- 클라이언트 검증은 UX 보조이고, 차례/시간/조건/중복/사전 존재/점수/패널티 판정은 Backend match domain이 최종 결정한다는 기준을 추가했다.
- 실패한 제출도 WebSocket event로 패널티와 선택적 후보 힌트를 내려줄 수 있다는 정책을 정리했다.

## [2026-06-13] maintenance | Clarify repeated lobby join event

- `realtime-websocket.md`와 `sunset-game-domain.md`에 반복 room join 요청은 REST 응답만 반환하고
  `lobby.room.joined` WebSocket event를 보내지 않는다는 기준을 정리했다.
- `lobby.room.joined`는 신규 멤버가 추가된 경우(`already_member=false`)에만 broadcast한다는 계약으로
  명확히 했다.

## [2026-06-13] maintenance | Align timestamps on KST

- `runtime-configuration.md`의 DB timestamp 기준을 UTC가 아니라 KST timezone-aware datetime으로 정정했다.
- 서버가 생성해 public API와 WebSocket payload로 내보내는 timestamp도 KST offset을 포함한다는 기준을 정리했다.

## [2026-06-13] maintenance | Add lobby room snapshot contract

- `realtime-websocket.md`와 `sunset-game-domain.md`에 `/ws/lobby/rooms/{room_public_id}` 연결 성공 직후 `lobby.room.snapshot`으로 현재 활성 멤버 목록을 초기화한다는 계약을 추가했다.
- Snapshot 이후 멤버 변경은 `lobby.room.joined`, `lobby.room.left` event로 반영한다는 클라이언트 상태 관리 기준을 정리했다.

## [2026-06-13] maintenance | Complete lobby leave contract

- `realtime-websocket.md`와 `sunset-game-domain.md`에 로비 목록의 현재 유저 active membership 응답, REST room leave, 방장 승계, 마지막 멤버 퇴장 시 room 폐쇄 기준을 반영했다.
- `lobby.room.left` event가 REST 퇴장과 WebSocket grace leave 모두에서 같은 퇴장 결과 payload를 전달한다는 기준을 정리했다.

## [2026-06-13] maintenance | Clarify Postman WebSocket collection format

- `openapi-swagger.md`에 Postman file import의 collection v2.1 JSON은 `ws://` URL도 HTTP
  request로 import하고, 내부 `ws-raw-request` JSON은 일반 import 포맷으로 인식되지 않는다는
  기준을 추가했다.
- 이 스크립트는 WebSocket 전용 Postman collection JSON을 생성하지 않고, WebSocket 요청은
  Postman UI에서 직접 만들며 `sessionToken` environment 변수를 `Cookie` header로 재사용한다는
  기준을 정리했다.
- 로컬과 운영 WebSocket URL을 같은 변수로 전환할 수 있도록 WebSocket base URL은 host/port로 쪼개지
  않고 `baseWs` 하나로 관리한다는 기준을 반영했다.

## [2026-06-13] maintenance | Clarify game session public ID naming

- `sunset-game-domain.md`와 API 문서 기준에서 게임 한 판의 공개 식별자는 `session_public_id`가 아니라 `game_session_public_id`로 부른다는 명명 기준을 반영했다.
- `game_session_public_id`는 라운드 ID가 아니며, 라운드/턴은 같은 game session 안의 phase 또는 round number로 관리한다는 구분을 명확히 했다.

## [2026-06-13] maintenance | Separate match resume token from login session

- `sunset-game-domain.md`에 `game_session_public_id`는 게임 세션 공개 식별자이고, `game_session_token`은 현재 실제 유저 참가자에게만 발급되는 match 복구 credential이라는 기준을 추가했다.
- `sunset-game-database-design.md`에 `game.session_participants.resume_token_hash`, `resume_token_expires_at` 컬럼과 partial index 기준을 추가했다.
- 로그인 `session_token` 만료는 진행 중 match를 즉시 끊지 않고, `/ws/match` 재연결은 `game_session_token`으로 participant identity를 복원할 수 있다는 기준을 남겼다.

## [2026-06-13] maintenance | Add BE Postman generation policy

- `openapi-swagger.md`에 Postman import용 JSON은 BE OpenAPI schema와 명시 WebSocket 정의에서 생성하고, HTTP API collection과 WebSocket collection을 별도 파일로 관리하며, Agent 서버와 BE `/api/v1/agent/*` proxy endpoint는 제외한다는 기준을 추가했다.
- Postman environment에서 `baseUrl`, `baseWs`, 인증/session, room/session 예시 변수를 관리하고, 로그인/회원가입 응답의 `session_token` 쿠키를 `sessionToken` 변수에 저장한다는 기준을 남겼다.

## [2026-06-12] maintenance | Add game API enum contract

- `sunset-game-domain.md`와 `openapi-swagger.md`에 `game_type`, room/session `status`, `participant_type` 같은 공개 API의 닫힌 문자열 값은 enum으로 관리하고 Swagger에 enum 목록을 노출한다는 기준을 추가했다.

## [2026-06-12] maintenance | Split signup and login auth contract

- `backend-guidelines.md`와 `2026-06-05-auth-session-login.md`에 `POST /api/v1/auth/signup`은 신규 계정 생성, `POST /api/v1/auth/login`은 기존 계정 인증만 담당한다는 기준을 반영했다.
- 로그인 request는 `account_id`, `password`만 받고, 회원가입 중복 계정/닉네임은 `409 AUTH_USER_CONFLICT`로 처리한다는 계약을 남겼다.

## [2026-06-12] maintenance | Clarify Grafana dashboard link policy

- `observability-stack.md`에 Grafana dashboard 간 이동은 `type: link`와 `/d/<dashboard_uid>` URL을 사용하고, `type: dashboards`는 tag 기반 목록 확장용이라 빈 tag와 함께 쓰지 않는다는 기준을 추가했다.

## [2026-06-12] maintenance | Add generic WebSocket APM observability

- `observability-stack.md`에 WebSocket 연결, 메시지, 오류, 종료, 연결 지속 시간 metric과 낮은 cardinality label 기준을 추가했다.
- Grafana trace dashboard는 Auth 도메인 고정 패널이 아니라 service/repository layer 기준으로 조회하고, WebSocket APM dashboard는 별도 범용 dashboard로 관리한다는 기준을 남겼다.

## [2026-06-12] maintenance | Add room lobby heartbeat and grace leave policy

- `realtime-websocket.md`에 room 로비 WebSocket은 client `ping`을 heartbeat로 보고, 45초 timeout 후 연결을 닫으며, 90초 grace time 안에 재연결하지 않으면 DB 퇴장 처리한다는 기준을 추가했다.
- `sunset-game-domain.md`에 grace 퇴장 확정 시 `game.room_members.left_at`을 기록하고 같은 room 연결에 `lobby.room.left`를 broadcast한다는 기준을 남겼다.

## [2026-06-12] maintenance | Add REST room APIs and path-based lobby WebSocket

- `realtime-websocket.md`에 객실 목록 조회, 객실 생성, 객실 참여는 REST API가 담당하고 `/ws/lobby/rooms/{room_public_id}`는 활성 room member만 연결하는 path 기반 room 로비 WebSocket이라는 기준을 반영했다.
- `sunset-game-domain.md`에 room 생성 시 방장을 첫 room member로 등록하고, join 성공 후 같은 room WebSocket 연결에 `lobby.room.joined`를 broadcast한다는 현재 계약을 정리했다.

## [2026-06-12] maintenance | Restructure websocket docs format

- `realtime-websocket.md`에 `/ws-docs`는 한국어 사용자가 읽는 endpoint matrix, 공통 envelope, message direction, endpoint별 contract, error/close code 중심의 WebSocket reference 형식으로 관리한다는 기준을 추가했다.
- WebSocket message heading은 `요청(Request)`, `응답(Response)`, `이벤트(Event)`처럼 한국어를 우선하고, 목차는 큰 섹션만 보여주며, 유저 플로우는 작은 Mermaid sequence diagram 여러 개로 나누어 관리한다는 기준을 남겼다.

## [2026-06-12] maintenance | Add lobby websocket and room join contract

- `realtime-websocket.md`에 `/ws/lobby`의 세션 쿠키 인증, room 구독 메시지, `lobby.room.joined` broadcast 기준을 추가했다.
- `sunset-game-domain.md`에 room 참여는 REST API가 DB `game.room_members`에 저장하고, lobby WebSocket은 연결과 구독 상태만 process memory에 보관한다는 기준을 추가했다.

## [2026-06-12] maintenance | Add test coverage threshold

- `code-conventions.md`에 `pytest`가 전체 `app` package coverage를 측정하고 총 coverage 90% 이상을 유지한다는 테스트 기준을 추가했다.

## [2026-06-12] maintenance | Add BE protected router session policy

- `backend-guidelines.md`에 BE REST API는 public router와 protected router를 분리하고, protected router에서 `session_token` 기반 `get_current_user` dependency를 공통 적용한다는 기준을 추가했다.
- 로그인과 health 계열 API만 public router에 두고, 새 BE API는 기본적으로 protected router에 등록한다는 운영 기준을 남겼다.

## [2026-06-12] maintenance | Add WebSocket docs TOC and Mermaid flow

- `realtime-websocket.md`에 `/ws-docs` 렌더러가 heading 기반 자동 목차와 Mermaid code block 렌더링을 지원한다는 문서 운영 기준을 추가했다.
- `ws-api.md`에는 게임 시작 REST gate, lobby broadcast, match 연결 권한 확인 흐름을 Mermaid sequence diagram으로 유지한다는 기준을 남겼다.

## [2026-06-11] maintenance | Add game session REST gate contract

- `sunset-game-domain.md`에 게임 진행 WebSocket 전 단계로 REST 기반 게임 시작과 세션 진입 권한 확인 기준을 추가했다.
- 로그인 `session_token`으로 현재 유저를 확인하고, 게임 시작 시 고정된 `session_participants`만 세션 진입을 허용하는 기준을 남겼다.
- `/ws/realtime`은 계속 연결 테스트용이며 이후 `/ws/lobby`, `/ws/match`가 같은 참가자 권한 기준을 재사용해야 한다고 정리했다.
- REST handler에서 lobby WebSocket 알림이 필요하면 connection manager 또는 서버 간 event bus로 이미 열린 연결에 broadcast하고, match 연결 후에는 `game_session_id + participant_id + user_id` identity를 기준으로 진행한다는 기준을 추가했다.
- start API는 room row lock으로 같은 room의 동시 요청을 직렬화하고, active session이 이미 있으면 기존 `game_session_public_id`를 반환하는 멱등 기준을 추가했다.

## [2026-06-11] maintenance | Add Sunset game DB design draft

- `sunset-game-database-design.md`에 해질녘 게임 플랫폼의 결과/복구 중심 DB 저장 범위와 table 초안을 정리했다.
- UUID v7은 row 식별자와 외부 노출 식별자에 쓰고, 게임 안 순서/번호/점수/개수는 integer로 둔다는 기준을 추가했다.
- `session_phases`, `participant_actions`, `state_snapshots`, `game_events`를 공통 진행 기록으로 두고 단어 게임은 `word_game` 확장 table로 분리하는 기준과 Mermaid ERD를 추가했다.

## [2026-06-11] maintenance | Split lobby and match WebSocket direction

- `realtime-websocket.md`에서 `/ws/realtime`을 실제 게임 상태가 아닌 ping/pong 연결 테스트용 endpoint로 정리했다.
- `sunset-game-domain.md`와 결정 기록에 실제 게임 통신은 `/ws/lobby`, `/ws/match`로 처음부터 분리한다는 기준을 반영했다.
- 기획 점검 결과 투표 시점을 라운드 종료가 아니라 게임/모든 라운드 종료 이후로 정리하고, AI 우승/보상, 점수 구간, 라운드 단위는 열린 질문으로 남겼다.

## [2026-06-11] ingest | Add Kkutu reference takeaways

- `sunset-game-domain.md`에 Kkutu 분석에서 참고할 빠른 시작 상태 머신, lobby/match WebSocket 관심사 분리, command-response와 broadcast 분리 기준을 반영했다.
- 로비/객실/매치 snapshot, 재접속 복구, 경기 화면 상태 분리, 게스트 플레이 여부를 향후 결정 지점으로 정리했다.

## [2026-06-11] ingest | Add Sunset game domain model

- `sunset-game-domain.md`에 해질녘 게임의 로비, 객실, 게임 세션, 라운드, 턴, 점수, 투표 도메인 기준을 정리했다.
- WebSocket은 BE가 권위 있는 게임 상태를 유지하고 snapshot/event로 클라이언트를 동기화하는 방향으로 정리했다.
- Agent는 AI 손님의 단어 후보만 제공하고 게임 상태, 점수, 투표 계산은 Backend가 소유한다는 경계를 명시했다.

## [2026-06-11] maintenance | Simplify Agent word payload

- Backend의 `game_type`은 handler 선택에 사용하고 Qdrant payload에는 저장하지 않는 기준을
  기록했다.
- Qdrant payload를 단어 구조 필드와 `used_count`로 제한하고 `used_words`를 `word`
  블랙리스트로 제외하는 검색 계약을 기록했다.

## [2026-06-11] maintenance | Add Qdrant-first vLLM fallback policy

- Qdrant 후보가 있으면 최대 10개 무작위 후보군에서 하나를 반환하는 선택 정책을 기록했다.
- 세 게임 후보가 없을 때 game type별 vLLM 프롬프트로 2~4글자 단어를 생성하고 규칙과 중복을
  검증하는 기준을 추가했다.
- 생성 단어의 사전 등재 여부는 외부 사전 없이 완전히 보장할 수 없고 Qdrant에 자동 적재하지 않는다고 명시했다.

## [2026-06-11] maintenance | Add BE to Agent health runtime contract

- `runtime-configuration.md`에 BE가 Agent health API를 호출할 때 전용 client wrapper와 배포 주입 설정을 사용한다는 기준을 추가했다.
- Agent 연결 정보는 기본값 없이 GitHub Secrets에서 필수로 주입한다는 배포 기준을 정리했다.

## [2026-06-11] implementation | Integrate Qdrant Agent MVP

- 별도 Agent 작업공간의 끝말잇기 MVP를 monorepo `app/agent` 소유 구조로 이식했다.
- Qdrant repository, game handler, 후보 선택, 멱등성, 비동기 적재와 사용 횟수 갱신 계층을 추가했다.
- 프롬프트는 `.txt`가 아닌 `app/agent/prompts.py` 변수로 관리한다.
- 단일 Docker image에서 `APP_MODULE=agent`, `PORT=8001`로 실행하도록 k3s manifest를 추가했다.
- Qdrant local PV와 vLLM 단일 GPU replica, 모델 hostPath, `enableServiceLinks=false`를 배포 기준으로 고정했다.
- 회사 NodePort `31080`에서 Azure localhost로 이어지는 SSH reverse tunnel과 Azure Nginx를 외부 연결 경계로 기록했다.
- Agent API, 한국어 처리, Qdrant 중복 적재, k3s manifest 테스트를 추가했다.

## [2026-06-11] maintenance | Separate socket router from API router

- `realtime-websocket.md`에 WebSocket endpoint는 REST API router 밖의 `/ws/realtime`, 문서 페이지는 `/ws-docs`로 둔다는 계약을 반영했다.
- `backend-guidelines.md`에 WebSocket route는 `/ws/{feature}` 형식으로 통일하고 `app/{server}/api/socket_router.py`에서 조립한다는 기준을 정리했다.

## [2026-06-11] maintenance | Add registered route guard policy

- `backend-guidelines.md`에 등록된 HTTP route path만 통과시키고 미등록 path는 감사 로그 전에 body 없는 `404`로 차단하는 기준을 추가했다.
- route guard가 차단한 path는 Uvicorn access log에서도 필터링한다는 로그 노이즈 관리 기준을 남겼다.
- `/docs`, `/redoc`, `/openapi.json`은 등록된 문서 route로 계속 열어두는 기준을 명시했다.

## [2026-06-11] maintenance | Add commit message convention

- `code-conventions.md`에 `<type>: <english summary>` 형식의 한 줄 영어 커밋 메시지 기준을 추가했다.
- 허용 type과 summary 작성 규칙을 AI 작업용 컨벤션으로 정리했다.

## [2026-06-11] lint | Clarify LLM Wiki scope and log policy

- `llm-wiki/wiki/llm-wiki-maintenance.md`를 추가해 위키에 남길 정보와 남기지 않을 코드 변경 이력의 경계를 명시했다.
- 과거 `log.md` 항목을 코드 변경 상세가 아니라 위키 지식 변경 단위로 압축했다.
- `llm-wiki/index.md`와 `AGENTS.md`에 `log.md`를 코드 변경 로그로 쓰지 않는 기준을 연결했다.

## [2026-06-11] maintenance | Add realtime WebSocket contract knowledge

- `realtime-websocket.md`에 BE realtime WebSocket endpoint, JSON envelope, `ping`/`realtime.pong`, validation close code 기준을 정리했다.
- WebSocket 전용 문서 원본과 API-served docs route를 함께 갱신해야 한다는 문서 관리 기준을 남겼다.

## [2026-06-10] maintenance | Consolidate observability and logging knowledge

- `observability-stack.md`에 OpenTelemetry, Prometheus, Tempo, Loki, Promtail, Grafana의 데이터 흐름과 dashboard 기준을 통합했다.
- 파일 로그, Uvicorn 로그 연결, log rotation/retention, Promtail label 추출, Loki/Grafana 조회 기준을 현재 운영 규칙으로 정리했다.
- metric label cardinality, trace span attribute, 민감값 제외 기준을 관측 작업의 재사용 지식으로 남겼다.

## [2026-06-10] maintenance | Consolidate runtime and deployment configuration knowledge

- `runtime-configuration.md`에 KST 서버 타임존, CORS allowlist, Docker runtime, Docker Hub image tag, 배포 `.env`, 로그 디렉터리, Docker network 기반 OTLP endpoint 기준을 통합했다.
- GitHub Actions Docker 배포와 운영 DB migration workflow는 실행 절차가 아니라 앞으로 따라야 할 runtime/deployment 계약으로 요약했다.
- `database-migrations.md`에는 SSH tunnel 기반 운영 DB migration 기준과 concurrency/confirmation 규칙을 반영했다.

## [2026-06-09] maintenance | Replace application gRPC knowledge with HTTP boundary

- `decisions/2026-06-09-remove-application-grpc.md`에 애플리케이션 gRPC를 제거하고 FastAPI HTTP와 기능별 client wrapper를 서버 간 통신 기준으로 삼는 결정을 남겼다.
- gRPC status 기준은 HTTP status와 WebSocket close code 기준으로 대체되었음을 관련 결정 문서에 표시했다.

## [2026-06-09] maintenance | Update auth account and runtime port rules

- 인증 PoC 기준을 계정 ID 기반 가입 겸 로그인 흐름으로 갱신하고 `users.users.account_id`를 로그인 식별자로 관리하도록 정리했다.
- 서버 HTTP host/port, Docker Compose 인프라 port, OpenTelemetry 기본 활성화 기준을 runtime 지식으로 정리했다.

## [2026-06-06] maintenance | Add API error and OpenAPI operation rules

- `openapi-swagger.md`에 public HTTP endpoint의 `response_model`, `status_code`, `summary`, `operation_id`, 실패 응답 문서화 기준을 정리했다.
- 공통 response envelope, `AppException`, error code catalog, Swagger error example 기준을 API 계약 지식으로 남겼다.
- Swagger 표시 문구와 schema 테스트를 언제 고정할지에 대한 테스트 기준을 정리했다.

## [2026-06-05] maintenance | Add database and user identity knowledge

- `database-schema-conventions.md`와 `database-migrations.md`에 UUID v7, PostgreSQL `text`, 내부/외부 관리번호, Alembic migration 운영 기준을 정리했다.
- 유저 도메인은 `users` schema를 사용하고, 내부 join 식별자와 외부 노출 식별자를 분리한다는 결정을 남겼다.
- PoC 유저 테이블과 세션 로그인 결정 기록을 추가했다.

## [2026-06-05] maintenance | Separate human docs and AI wiki roles

- `docs/`는 사람이 보는 문서, `llm-wiki/`는 AI 작업 지식 레이어라는 역할 분리를 결정 기록으로 남겼다.
- FastAPI/WebSocket 가이드라인과 Python 코드 컨벤션의 AI 작업 기준을 `llm-wiki/wiki/`에 둔다고 정리했다.
- 한국어 주석/docstring 기준과 레이어별 테스트 기준을 AI 작업용 컨벤션에 반영했다.

## [2026-06-05] ingest | Backend framework and code conventions

- 사람용 backend/code convention 문서의 핵심을 AI 작업 기준으로 컴파일해 `backend-guidelines.md`, `code-conventions.md`, `backend-guidelines-summary.md`에 반영했다.
- FastAPI, WebSocket, 서버 간 client wrapper, 레이어 책임, 테스트 기준을 초기 작업 지식으로 정리했다.

## [2026-06-05] maintenance | LLM Wiki bootstrap

- `llm-wiki/index.md`를 콘텐츠 카탈로그로 만들고 `log.md`를 위키 작업 이력으로 분리했다.
- `current-status.md`, `project-map.md`, Karpathy LLM Wiki 개념, 초기 결정/출처 페이지를 추가했다.
- 위키를 읽거나 갱신할 때 `index.md`를 먼저 확인한다는 운영 기준을 세웠다.
