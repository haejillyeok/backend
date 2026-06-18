# YYYY-MM-DD Incident or Learning Title

- Status: draft | reviewed | closed
- Date: YYYY-MM-DD
- Owner:
- Participants:
- Severity: low | medium | high | critical
- Related issue/PR:
- Related ADR:
- Related wiki:

## Executive Summary

1~3문장으로 무슨 일이 있었고, 영향은 무엇이었으며, 핵심 원인은 무엇인지 요약한다.

## Impact

사용자, 개발, 운영, 일정에 준 영향을 구분해서 쓴다. 영향이 없었던 영역은 "No known impact"라고 쓴다.

- User impact:
- Developer impact:
- Operational impact:
- Schedule impact:

## Detection

어떻게 발견했는지 쓴다.

- Detected by:
- First signal:
- Detection gap:

## Timeline

- HH:MM:
- HH:MM:
- HH:MM:

## What Happened

사건을 시간순으로 설명한다. 추측과 확인된 사실을 구분한다.

## Root Cause Analysis

### Direct Cause

직접적으로 실패를 일으킨 원인을 쓴다.

### Contributing Factors

- 

### Why Existing Safeguards Did Not Catch It

- 

## What Went Well

- 

## What Went Wrong

- 

## Corrective Actions

| Action | Owner | Due | Status |
| --- | --- | --- | --- |
|  |  |  | open |

## Preventive Rules

다음에 같은 실수를 피하기 위해 앞으로 지킬 규칙을 쓴다. 코드 변경 이력이 아니라 재사용 가능한 기준으로 작성한다.

- 

## LLM Working Rule Update

재발 방지를 위해 `AGENTS.md`, `.codex/workflow/CONTEXT.md`, `llm-wiki/` 중 어디를 갱신해야 하는지 쓴다.

- Required: yes | no
- Target file/page:
- Rule summary:

## Closure Checklist

- [ ] 직접 원인과 기여 요인을 구분했다.
- [ ] 재발 방지 action item에 owner와 due를 적었다.
- [ ] 장기 기준이 된 항목을 `llm-wiki/`에 현재 규칙으로 반영했다.
- [ ] 관련 ADR이 필요하면 만들거나 연결했다.
