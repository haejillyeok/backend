---
title: Andrej Karpathy llm-wiki gist
type: source-summary
updated: 2026-06-05
source_url: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
---

# Andrej Karpathy llm-wiki gist

## Source

- Andrej Karpathy, `llm-wiki.md`, created 2026-04-04.
- URL: <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>

## Summary

Karpathy의 LLM Wiki 패턴은 RAG처럼 원본 조각을 매 질문마다 다시 찾는 대신, LLM이 원본 자료를 구조화된 Markdown 위키로 점진적으로 컴파일하고 유지하게 한다.

핵심은 세 계층이다.

- Raw sources: 원본 자료이며 source of truth다.
- Wiki: LLM이 작성하고 관리하는 요약, 개념, 비교, 연결, 결정의 Markdown 레이어다.
- Schema: LLM에게 위키 구조와 운영 규칙을 알려주는 `AGENTS.md` 또는 `CLAUDE.md` 같은 지침 파일이다.

운영 파일은 두 가지가 중요하다.

- `index.md`: 위키 전체 콘텐츠 카탈로그다. 답변 전 먼저 읽고 관련 페이지로 이동한다.
- `log.md`: ingest, query, lint 같은 작업을 시간순으로 기록한다.

## Applied Here

- Raw sources: `llm-wiki/raw/`
- Wiki: `llm-wiki/wiki/`
- Schema: `AGENTS.md`
- Index: `llm-wiki/index.md`
- Log: `llm-wiki/log.md`

## Notes

- 현재 레포 규모에서는 별도 vector DB보다 Markdown 인덱스와 `rg` 검색이 적합하다.
- 이 레포에서는 `docs/`를 사람 전용 문서로 두고, AI 작업에 필요한 지식은 `llm-wiki/`에 유지한다. 코드, 설정, 테스트가 최종 사실 기준이다.
