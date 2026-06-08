---
title: Docs vs LLM Wiki
type: decision
date: 2026-06-05
status: accepted
---

# Docs vs LLM Wiki

## Decision

`docs/`와 `llm-wiki/`의 역할을 분리한다.

- `docs/`: 사람이 보는 문서
- `llm-wiki/`: AI가 작업할 때 사용하는 전체 지식 레이어

## Rationale

사람이 읽기 좋은 API 설명, 아키텍처 설명, 개발 절차는 `docs/`에 둔다. `docs/`는 사람 전용 뷰다.

AI가 작업할 때 필요한 코드 컨벤션, 프레임워크 가이드라인, 결정 기록, 요약, 연결, 질문, 임시 분석은 `llm-wiki/`에 둔다. 이 레이어는 LLM이 매번 같은 내용을 다시 찾지 않도록 돕는 기억 장치이며, AI 작업의 기본 참조점이다.

## Duplication Rule

`docs/`에 있는 내용이 AI 작업에도 필요하면 `llm-wiki/`에도 정리한다.

코드 컨벤션이나 가이드라인처럼 AI가 작업 중 직접 따라야 하는 정보는 `docs/`에만 있으면 안 된다.

## Consequences

- 코드, 설정, 테스트가 최종 사실 기준이다.
- `llm-wiki/`는 AI 작업을 위한 compiled knowledge다.
- `docs/`는 사람이 보는 문서이므로, AI 작업 기준은 `llm-wiki/`에 유지한다.
