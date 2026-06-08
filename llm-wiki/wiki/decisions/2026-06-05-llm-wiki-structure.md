---
title: LLM Wiki Structure
type: decision
date: 2026-06-05
status: accepted
---

# LLM Wiki Structure

## Decision

backend 레포의 LLM Wiki는 루트 `llm-wiki/` 아래에 둔다.

## Structure

- `llm-wiki/raw/`: 원본 자료
- `llm-wiki/wiki/`: LLM이 유지하는 Markdown 위키
- `llm-wiki/index.md`: 콘텐츠 인덱스
- `llm-wiki/log.md`: 작업 로그

## Rationale

- 사용자가 명시적으로 `llm-wiki`를 요청했다.
- Karpathy 패턴의 핵심인 raw, wiki, schema 레이어를 파일 시스템만으로 표현할 수 있다.
- `index.md`와 `log.md`를 분리하면 현재 지식 지도와 시간순 변경 이력을 각각 관리할 수 있다.
- 별도 DB나 vector store 없이도 현재 규모에서는 Markdown과 `rg`만으로 충분하다.

## Consequences

- LLM이 위키 페이지를 만들거나 수정하면 `llm-wiki/index.md`와 `llm-wiki/log.md`를 함께 갱신해야 한다.
- 코드, 설정, 테스트와 충돌하는 위키 내용은 최신 사실 기준에 맞춰 갱신한다.
- 위키가 커지면 검색 스크립트나 Markdown 검색 도구를 추가할 수 있다.
