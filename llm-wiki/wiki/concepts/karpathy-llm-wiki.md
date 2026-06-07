---
title: Karpathy LLM Wiki
type: concept
updated: 2026-06-05
source: ../sources/karpathy-llm-wiki-gist.md
---

# Karpathy LLM Wiki

Karpathy LLM Wiki는 LLM이 원본 자료를 매번 다시 검색해서 답하는 방식 대신, 원본을 읽고 유지 가능한 Markdown 위키로 컴파일해 지식이 누적되게 하는 패턴이다.

## Layers

1. Raw sources
   - 원본 자료다.
   - LLM은 읽지만 수정하지 않는다.
   - 이 레포에서는 `llm-wiki/raw/`가 해당한다.

2. Wiki
   - LLM이 작성하고 갱신하는 Markdown 지식 레이어다.
   - 요약, 개념, 결정, 출처, 열린 질문을 연결한다.
   - 이 레포에서는 `llm-wiki/wiki/`가 해당한다.

3. Schema
   - LLM이 어떤 규칙으로 위키를 운영할지 정하는 파일이다.
   - 이 레포에서는 루트 `AGENTS.md`가 해당한다.

## Operating Pattern

- Ingest: 원본 자료를 읽고 기존 위키에 통합한다.
- Query: 답변 전 인덱스를 읽고 관련 위키 페이지를 확인한다.
- Lint: 모순, 오래된 주장, 깨진 링크, 고아 문서를 주기적으로 점검한다.
- Writeback: 보존 가치가 있는 답변, 결정, 비교는 위키로 되돌려 쌓는다.

## Local Rule

이 레포에서는 `llm-wiki/index.md`를 항상 최신 카탈로그로 유지한다. 새 페이지가 생겼는데 인덱스가 갱신되지 않았다면 작업이 끝난 것이 아니다.
