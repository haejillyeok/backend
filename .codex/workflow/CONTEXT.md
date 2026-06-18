# Codex Workflow Context

이 파일은 Codex 세션 시작 시 읽는 얇은 진입점이다. 실제 장기 지식은 `llm-wiki/`가 기준이고,
이 폴더는 Codex 작업 운영 흐름만 관리한다. 사람이 함께 읽어야 하는 ADR과 postmortem은 `docs/`에 둔다.

## Session Start

1. 먼저 `llm-wiki/index.md`를 읽고 작업과 관련된 위키 페이지를 찾는다.
2. 이 파일을 읽고 ADR, postmortem, state 기준을 확인한다.
3. 최근 중단/진행 상태가 필요하면 `.codex/workflow/STATE.md`를 확인한다.
4. 구조적 결정이 필요하면 `docs/adr/index.md`와 관련 ADR을 확인한다.
5. 반복 실패, 장애, 검증 누락, 운영 사고가 의심되면 `docs/postmortems/index.md`를 확인한다.

## Project Identity

`해질녘(SUNSET)`은 호텔 테마의 웹 기반 모바일 반응형 멀티플레이어 게임이다. 플레이어는 로비에서
객실에 입장해 단어 게임을 진행하고, 게임 종료 후 함께 플레이한 손님 중 초대받지 않은 손님인
AI 플레이어를 투표로 찾아낸다.

제품의 감각은 "해가 지는 호텔", "가면을 쓴 손님", "초대받지 못한 손님", "객실에서 벌어지는 실시간
게임"에 있다. 구현은 단순한 단어 API가 아니라 이 게임 경험을 안정적으로 진행시키는 서버 상태 머신을
만드는 일이다.

## Domain North Star

- 서버가 게임 상태의 권위자다. 클라이언트는 snapshot/event를 렌더링하고, 최종 사실은 Backend가 가진다.
- `Room`은 참가자가 대기하고 설정을 조정하는 객실이고, `GameSession`은 한 객실에서 시작되어 결과가
  확정될 때까지의 실행 단위다.
- `Guest`는 게임 참가 단위다. 실제 User일 수도 있고, 게임 시작 시 추가되는 AI 손님일 수도 있다.
- `Uninvited Guest`는 AI 손님이다. 대기방에 미리 포함하지 않고 게임 시작 시 추가하며, 정체는 결과 공개
  전까지 숨긴다.
- `Round`는 끝말잇기 한판이고, `Cycle`은 한 Round 안에서 모든 Guest가 한 번씩 Turn을 가진 한 바퀴다.
  Cycle과 Round를 섞지 않는다.
- `Turn`, `Submission`, `ScoreLedger`, `Vote`는 게임의 핵심 기록이다. 최종 점수만 저장하지 말고
  점수 변화 사유를 남긴다.

## Backend and Agent Boundary

- Backend는 방, 참가자, 세션, 라운드, 턴, 타이머, 사용 단어, 점수, 투표, 결과를 소유한다.
- Agent는 AI 손님의 단어 후보를 제공한다.
- Agent는 턴 순서, 라운드 종료, 투표, 정체 공개, 점수 계산을 결정하지 않는다.
- Backend는 Agent 답변도 다시 서버 게임 규칙과 사전 기준으로 검증한다.

## Realtime Shape

- `/ws/realtime`은 ping/pong 연결 테스트용이다. 게임 상태를 다루지 않는다.
- `/ws/lobby/rooms/{room_public_id}`는 참여가 허용된 객실의 대기방 snapshot, 입장/퇴장, 설정 변경,
  시작 handoff를 맡는다.
- `/ws/match`는 실제 게임 세션, 라운드, 턴, 단어 제출, 점수, 투표, 결과를 맡는다.
- WebSocket event는 사용자 경험의 흐름을 만든다. 메시지를 추가하거나 바꿀 때는 재접속 snapshot,
  server time, 권한 경계, 공개 가능한 payload를 함께 고려한다.

## Implementation Attitude

- 화면 전환보다 상태 전이를 먼저 본다.
- 새로운 기능은 호텔/객실/손님/가면/초대받지 못한 손님이라는 도메인 언어에 맞춰 이름 붙인다.
- AI 내부 실패 사유나 정체 정보는 결과 공개 전 사용자-facing payload로 새지 않게 한다.
- 실시간 게임에서 timeout, stale event, reconnect, late submit 같은 edge case는 정상 경로만큼 중요하다.
- 자세한 도메인 계약은 `llm-wiki/wiki/sunset-game-domain.md`와 `docs/sunset-domain.md`를 기준으로 확인한다.

## Knowledge Boundaries

- `llm-wiki/`: AI가 다음 작업에서 재사용할 프로젝트 지식의 canonical layer.
- `.codex/workflow/`: Codex 세션 운영 규칙과 현재 작업 상태.
- `docs/adr/`: 사람이 함께 읽는 구조적 결정과 대안, 결과를 남기는 결정 기록.
- `docs/postmortems/`: 사람이 함께 읽는 반복 실패, 장애, 사고, 큰 시행착오를 재발 방지 규칙으로 압축하는 회고.
- `docs/`: 사람이 읽는 프로젝트 문서. AI 작업 기준으로 재사용할 내용은 `llm-wiki/`에도 반영한다.

## Borrowed Workflow Shape

- GSD에서 phase thinking을 차용한다: discuss/decide before plan, plan before execute, verify before ship.
- gstack에서 specialist review 감각을 차용한다: architect, reviewer, QA, release 관점을 분리한다.
- Superpowers에서 검증 규율을 차용한다: TDD가 필요한 변경은 실패 테스트부터 시작하고, 완료 주장은 fresh verification 뒤에만 한다.
- flow-kit에서 artifact gate를 차용한다: 중요한 상태는 대화 기억이 아니라 Markdown 산출물에 남긴다.

## ADR Gate

Codex는 작업 시작과 설계 중 ADR 필요 여부를 먼저 판단한다. 사용자가 ADR 작성을 명시하지 않아도,
구조적 결정이 있으면 새 ADR을 만들거나 기존 ADR 관계를 확인한다.

다음 중 하나라도 해당하면 ADR을 만든다.

- 모듈 경계, public API, WebSocket 계약, DB schema 정책, 배포/운영 기준이 바뀐다.
- 되돌리기 어려운 기술 선택을 한다.
- 두 개 이상의 합리적 대안이 있고 선택 이유가 다음 작업자의 판단을 바꾼다.
- 기존 `llm-wiki/` 결정과 충돌하거나 대체한다.

이미 `accepted` 된 ADR은 결정의 역사로 보존한다. 오타, 링크, 관련 PR, 관련 위키 같은 비의미적
정정만 기존 ADR에 반영하고, 결정, 근거, trade-off, consequence가 바뀌면 기존 ADR을 고치지 않고
새 ADR을 만들어 `Supersedes` / `Superseded by`로 연결한다.

ADR을 만들었다면 `docs/adr/index.md`에 추가한다. 앞으로의 AI 작업 기준이 바뀌면 `llm-wiki/`에는
작업 내역이 아니라 현재 따라야 할 기준만 요약한다.

## Postmortem Gate

다음 중 하나라도 해당하면 postmortem을 작성한다.

- 같은 원인으로 같은 실패가 두 번 이상 반복됐다.
- 테스트나 검증 없이 완료를 주장했다가 틀렸다.
- schema migration, transaction, WebSocket state, 배포/운영에서 재발 가능한 사고가 있었다.
- 디버깅 과정에서 다음 작업자가 반드시 알아야 할 함정이 드러났다.

Postmortem의 action item 중 장기 기준이 된 항목은 `llm-wiki/`에 현재 규칙으로 반영한다.

## Completion Gate

작업 완료 전 확인한다.

- 코드 변경은 적절한 테스트나 검증을 실행했다.
- `docs/adr/` 또는 `docs/postmortems/`를 만들었다면 각 index를 갱신했다.
- `llm-wiki/`를 변경했다면 `llm-wiki/index.md`와 `llm-wiki/log.md` 기준을 지켰다.
- 변경 범위가 사용자의 요청과 직접 관련된 파일에 머문다.
