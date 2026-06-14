---
title: Test Page Harness
type: development-tool
updated: 2026-06-14
audience: ai
---

# Test Page Harness

`test-page/`는 현재 BE 기능을 브라우저에서 직접 호출해보는 테스트용 서브 프로젝트다.
제품 프론트엔드로 가져갈 화면은 아니지만, 기본 UI는 사용자가 실제 게임 페이지처럼 체크인, 로비,
객실 대기, 게임 진행을 의심 없이 따라갈 수 있게 구성한다. REST/API 원본 응답과 연결 기록은
기본 흐름에 노출하지 않고 숨김 운영 노트에 둔다.

## Runtime

- 실행 위치: `test-page/`
- 실행 명령: `npm run dev`
- 기본 URL: `http://localhost:3000`
- 연결 가능한 BE base URL: `http://localhost:8000`, `https://api.haejillyeok.com`
- 요청 URL 환경변수: `VITE_BE_TARGET`, `VITE_BE_LOCAL_BASE_URL`, `VITE_BE_PROD_BASE_URL`

BE CORS allowlist에는 credentialed cookie flow를 위해 `http://localhost:3000`이 포함된다.
테스트 페이지는 Agent 서버를 직접 호출하지 않고, 필요한 Agent 연결 상태는 BE `/api/v1/agent/health`를
통해 확인한다.

## Covered Surfaces

- BE health, Swagger, `/ws-docs`
- `/api/v1/auth/login`, `/api/v1/auth/signup`
- `/api/v1/game/rooms` list/create/update/join/leave/start
- `/api/v1/game/sessions/{game_session_public_id}/entry`
- `/ws/realtime` ping/pong
- `/ws/lobby/rooms/{room_public_id}` connect/ping/event log
- `/ws/match` connect/ping/`word.submit`/`vote.submit`/event log
- BE `/api/v1/agent/health`
- 숨김 운영 노트의 protected API session cookie 확인

## Flow

UI는 체크인, 로비, 객실 대기, 게임 진행 단계로 나뉜다.
로그인 또는 회원가입에 성공하면 로비로 이동하고, 객실 생성/입장에 성공하면 객실 대기 페이지로 이동해
Lobby WebSocket을 연결한다. 게임 시작에 성공하면 match session token을 저장하고 게임 진행 페이지로
이동해 Match WebSocket을 연결한다. Lobby `game.started` event를 받은 경우에는 session entry API로
토큰을 발급받은 뒤 게임 진행 페이지로 이동한다.

게임 진행 화면은 `match.snapshot.server_time`, `current_turn.deadline_at`, `voting_deadline_at`을 사용해
남은 시간을 표시한다. 화면 타이머는 표시용이며, 실제 timeout과 상태 전환은 계속 서버 deadline 판정이
권위자다. 현재 참가자 판정은 participant `is_me`와 `current_turn.actor_seat_number`를 비교해 내 턴이면
타이머, 배너, 단어 입력 영역을 강조한다.
Match WebSocket의 `match.turn.resolved` event는 원본 로그에만 남기지 않고 화면 상태에도 반영한다.
`accepted`는 `next_turn`으로 현재 턴과 phase id를 갱신하고, `rejected`/`failed`는 현재 턴을 유지한 채
사용자 notice로 판정 사유를 보여준다. `timeout`이나 `next_status`가 포함된 event는 다음 턴 또는 투표
상태 전환 표시를 갱신한다.
또한 Match WebSocket에서 받은 사용자-facing event는 `match.feed`에 정규화해 누적한다. 게임 진행 화면은
최근 판정을 큰 카드로 보여주고, 사이드 영역에는 최근 흐름을 쌓아 누가 어떤 단어를 냈고 서버가 어떻게
판정했는지 바로 읽을 수 있게 한다. 내 답변과 다른 손님의 답변은 별도 문구와 스타일로 구분한다.
`match.round.finished` event는 라운드 종료 피드로 정규화해 다음 라운드 시작 또는 투표 진입을 사용자에게
명확히 보여준다.
`match.round.started` event는 라운드 시작 피드로 정규화해 새 라운드 번호와 첫 차례 좌석을 사용자에게
바로 보여준다.

서버 선택, health 확인, Swagger와 WebSocket 문서 링크, `/ws/realtime` ping/pong, 원본 REST/WS 로그는
상단의 숨김 운영 노트 패널에 둔다. 기본 화면에는 `BE`, `API`, `WebSocket`, `Swagger`, raw identifier 같은
개발자용 표현을 노출하지 않는다.

로그인/회원가입 성공 시 발급되는 `session_token`은 HttpOnly cookie이므로 테스트 페이지 JS가 직접 읽어
header나 body에 넣지 않는다. 보호 REST 요청은 공통 `requestJson`에서 `credentials: "include"`를 사용해
브라우저가 쿠키를 포함하도록 한다. 숨김 운영 노트의 session 확인 동작은 `/api/v1/game/rooms` 같은
protected API를 호출해 쿠키 포함 여부를 확인한다.

## State Management

상태관리는 React `useReducer` 기반 단일 store로 관리한다. Store는 현재 페이지, 런타임 BE 설정,
로그인 유저, 객실 목록/선택 객실, 현재 멤버십, match 세션 식별자, match snapshot, WebSocket 연결
상태, 이벤트 로그, 숨김 운영 노트 open 상태, 사용자 notice와 busy action을 소유한다. 실제 `WebSocket`
객체는 React state에 넣지 않고 `useRef`로 보관하고, 연결 상태와 수신 event만 reducer action으로 반영한다.

## Design Notes

UI는 제공된 Figma 캡처를 그대로 복제하지 않고, 회색 작업 배경, 흰 패널, 빨간 액션 버튼,
호텔 정체성, 아바타 칩 같은 방향성만 참고한다. 테스트 페이지라도 주요 사용자 흐름이 먼저 보이도록 하고,
원본 응답과 WebSocket event log는 숨김 운영 노트로 분리한다.
