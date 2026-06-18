---
title: Codex Workflow
type: operating-guide
updated: 2026-06-18
audience: ai
---

# Codex Workflow

이 저장소는 `.codex/`를 Codex 전용 작업 운영 레이어로 사용한다. `.codex/`는 장기 지식 저장소가 아니라
세션 시작과 현재 작업 상태를 다루는 얇은 운영 레이어다. 사람이 함께 읽어야 하는 ADR과 postmortem은
`docs/` 아래에서 관리한다.

## Boundaries

- `llm-wiki/`는 AI가 다음 작업에서 재사용할 canonical knowledge layer다.
- `.codex/workflow/CONTEXT.md`는 Codex 세션 시작 진입점이다. 내용을 길게 누적하지 않고 읽을 위치와 gate만 안내한다.
- `.codex/workflow/STATE.md`는 active change, current phase, interrupted task처럼 현재 작업 상태만 짧게 기록한다.
- `docs/adr/`는 사람이 함께 읽는 의사결정 보고서로 구조적 결정의 배경, 대안, 결과, 검증 방법을 보존한다.
- `docs/postmortems/`는 사람이 함께 읽는 회고 보고서로 반복 실패, 장애, 검증 누락, 운영 사고를 재발 방지 규칙으로 압축한다.

## Session Start

Codex 세션을 시작하면 다음 순서를 따른다.

1. `llm-wiki/index.md`를 먼저 읽고 관련 페이지를 찾는다.
2. `.codex/workflow/CONTEXT.md`를 읽고 프로젝트 정체성, 도메인 북극성, ADR/postmortem gate를 확인한다.
3. 필요한 경우 `.codex/workflow/STATE.md`에서 중단 작업이나 active change를 확인한다.
4. 구조적 결정이 필요한 작업이면 `docs/adr/index.md`를 확인한다.
5. 반복 실패나 장애 맥락이 있으면 `docs/postmortems/index.md`를 확인한다.

`.codex/hooks/session_start_context.py`는 세션 시작 때 이 진입점을 노출하는 보조 장치다. hook 출력만으로
프로젝트 지식을 대체하지 않고, 필요한 Markdown 파일을 실제로 읽는다.

## ADR Gate

Codex는 작업 시작과 설계 중 ADR 필요 여부를 먼저 판단한다. 사용자가 ADR 작성을 명시하지 않아도,
구조적 결정이 있으면 새 ADR을 만들거나 기존 ADR 관계를 확인한다.

다음 중 하나라도 해당하면 ADR을 만든다.

- 모듈 경계, public API, WebSocket 계약, DB schema 정책, 배포/운영 기준이 바뀐다.
- 되돌리기 어려운 기술 선택을 한다.
- 두 개 이상의 합리적 대안이 있고 선택 이유가 다음 작업자의 판단을 바꾼다.
- 기존 `llm-wiki/` 결정과 충돌하거나 대체한다.

`accepted` ADR은 결정의 역사로 보존한다. 오타, 링크, 관련 PR, 관련 위키 같은 비의미적 정정만
기존 ADR에 반영하고, 결정, 근거, trade-off, consequence가 바뀌면 기존 ADR을 수정하지 않고 새 ADR을
만들어 `Supersedes` / `Superseded by`로 연결한다.

ADR은 `docs/adr/template.md`를 사용하고 `docs/adr/index.md`에 추가한다. ADR이 앞으로의 AI 작업 기준을
바꾸면 `llm-wiki/`에는 작업 내역이 아니라 현재 기준으로 요약한다.

## Postmortem Gate

다음 중 하나라도 해당하면 postmortem을 작성한다.

- 같은 원인으로 같은 실패가 두 번 이상 반복됐다.
- 테스트나 검증 없이 완료를 주장했다가 틀렸다.
- schema migration, transaction, WebSocket state, 배포/운영에서 재발 가능한 사고가 있었다.
- 디버깅 과정에서 다음 작업자가 반드시 알아야 할 함정이 드러났다.

Postmortem은 `docs/postmortems/template.md`를 사용하고 `docs/postmortems/index.md`에 추가한다.
Action item 중 장기 기준이 된 항목은 `llm-wiki/`에 현재 규칙으로 반영한다.

## Borrowed Workflow Shape

이 운영 레이어는 flow-kit을 그대로 복사하지 않는다. 다음 원칙만 이 저장소 기준으로 차용한다.

- GSD식 phase thinking: 결정 전 논의, 실행 전 계획, 완료 전 검증.
- gstack식 specialist review: architect, reviewer, QA, release 관점을 분리해 생각한다.
- Superpowers식 verification discipline: TDD가 필요한 변경은 실패 테스트부터 시작하고, 완료 주장은 fresh verification 뒤에만 한다.
- flow-kit식 artifact gate: 중요한 상태와 결정은 대화 기억이 아니라 Markdown 산출물에 남긴다.

## Completion Check

작업 완료 전 다음을 확인한다.

- 코드 변경은 적절한 테스트나 검증을 실행했다.
- `docs/adr/` 또는 `docs/postmortems/`를 만들었다면 각 index를 갱신했다.
- `llm-wiki/`를 변경했다면 `llm-wiki/index.md`와 `llm-wiki/log.md` 기준을 지켰다.
- 변경 범위가 사용자의 요청과 직접 관련된 파일에 머문다.

## Related

- [llm-wiki-maintenance.md](llm-wiki-maintenance.md)
- [concepts/karpathy-llm-wiki.md](concepts/karpathy-llm-wiki.md)
