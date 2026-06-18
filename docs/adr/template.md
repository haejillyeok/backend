# ADR-NNNN: Decision Title

- Status: proposed | accepted | superseded
- Date: YYYY-MM-DD
- Deciders:
- Consulted:
- Related issue/PR:
- Related wiki:
- Supersedes:
- Superseded by:

## Executive Summary

1~3문장으로 결정의 핵심을 요약한다. 바쁜 사람이 이 문단만 읽어도 무엇을 왜 선택했는지 알 수 있어야 한다.

## Background

결정이 필요해진 배경을 설명한다. 현재 상황, 제약, 도메인 요구, 운영 조건, 이전 결정과의 관계를 포함한다.

## Problem Statement

이번 ADR이 답해야 하는 질문을 명확히 쓴다.

예: "게임 진행 WebSocket을 로비와 매치로 분리할 것인가, 단일 endpoint로 유지할 것인가?"

## Decision Drivers

- 사용자 경험:
- 운영 안정성:
- 개발 복잡도:
- 테스트 가능성:
- 확장성:
- 되돌리기 비용:

## Decision

선택한 방향을 현재형으로 쓴다. 구현 세부 목록보다 앞으로 지켜야 할 결정 자체를 명확히 한다.

`accepted` 이후 이 결정의 의미를 바꾸지 않는다. 결정, 근거, trade-off, consequence가 바뀌면
이 ADR을 직접 수정하지 않고 새 ADR을 만들어 이 문서를 supersede한다.

## Options Considered

| Option | Summary | Pros | Cons | Decision |
| --- | --- | --- | --- | --- |
| A |  |  |  | accepted/rejected |
| B |  |  |  | accepted/rejected |
| C |  |  |  | accepted/rejected |

## Rationale

선택한 option이 decision drivers를 어떻게 만족하는지 설명한다. 단순히 "best practice"라고 쓰지 말고,
이 프로젝트의 도메인과 제약에 연결한다.

## Consequences

### Positive

- 

### Negative / Trade-offs

- 

### Risks

- 

### Mitigations

- 

## Implementation Notes

결정이 코드, 문서, 운영 절차에 주는 직접 영향을 적는다. 구현 상세가 아직 정해지지 않았다면 의도와 경계만 쓴다.

- Code:
- Tests:
- Docs:
- Operations:

## Rollout / Migration

기존 동작에서 전환이 필요하면 단계별 계획을 쓴다. 전환이 필요 없으면 "Not required"라고 쓴다.

1. 
2. 
3. 

## Validation

이 결정이 제대로 적용됐는지 확인할 방법을 쓴다.

- 

## Open Questions

- 

## LLM Wiki Update

이 결정이 앞으로의 AI 작업 기준을 바꾸면 `llm-wiki/`에 현재 규칙으로 반영한다.

- Required: yes | no
- Target page:
- Summary of rule to add:
