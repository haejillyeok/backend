# AGENTS.md

이 파일은 이 저장소에서 LLM이 코드를 읽고, 수정하고, 지식을 축적할 때 따르는 루트 운영 규칙입니다.

## Repository Map

- `README.md`: 로컬 개발과 실행 안내
- `docs/`: 사람이 보는 프로젝트 문서
- `docs/api.md`: REST API 계약
- `docs/architecture.md`: 서버 구조와 모듈 경계
- `docs/development.md`: 개발 환경, DB, 실행, 테스트 절차
- `docs/backend-guidelines.md`: 사람이 읽는 FastAPI, WebSocket 설명
- `docs/code-conventions.md`: 사람이 읽는 Python 코드 스타일과 레이어 규칙 설명
- `app/be/`: 백엔드 FastAPI 서버
- `app/agent/`: 에이전트 FastAPI 서버
- `app/shared/`: 두 서버가 공유하는 설정, 로깅, client helper
- `test/`: 테스트 코드
- `llm-wiki/`: AI가 작업할 때 사용하는 전체 프로젝트 지식 레이어
- `llm-wiki/raw/`: 원본 자료. LLM은 원칙적으로 수정하지 않는다.
- `llm-wiki/wiki/`: 원본과 작업 이력을 바탕으로 LLM이 유지하는 요약, 개념, 결정, 연결
- `llm-wiki/index.md`: LLM Wiki 콘텐츠 카탈로그. 위키를 읽거나 갱신하기 전에 먼저 확인한다.
- `llm-wiki/log.md`: LLM Wiki 작업 이력. ingest, query, lint, maintenance를 시간순으로 남긴다.

## Purpose

`docs/`는 사람이 보는 프로젝트 문서입니다. 사람이 읽기 좋은 설명, API 안내, 아키텍처 설명, 개발 절차를 여기에 둡니다.

`llm-wiki/`는 AI용 작업 기억이자 작업 지식 전체입니다. 코드 컨벤션, 프레임워크 가이드라인, 결정 기록, 요약, 열린 질문처럼 AI가 작업할 때 사용할 수 있는 모든 정보는 `llm-wiki/`에 있어야 합니다. Karpathy의 LLM Wiki 패턴처럼 원본 자료를 매번 다시 검색해서 답하는 대신, LLM이 원본을 읽고 구조화된 Markdown 위키로 컴파일해 프로젝트 지식이 누적되도록 합니다.

`docs/`에 사람이 읽는 문서를 추가하더라도, 그 내용이 AI 작업에 필요하면 `llm-wiki/`에도 정리합니다. AI는 작업 전 `docs/`보다 `llm-wiki/index.md`를 먼저 읽고, 필요한 경우 사람용 문서인 `docs/`를 보조 참고 자료로 확인합니다.

## Karpathy 4 Principles

1. Think Before Coding
   - 불명확한 요구는 조용히 추측하지 말고 가정을 명시한다.
   - 가능한 해석이 2개 이상이면 선택지와 trade-off를 드러낸다.
   - 요구, 코드, 문서 사이의 충돌을 발견하면 먼저 짚고 넘어간다.

2. Simplicity First
   - 지금 필요한 최소 구현과 문서만 만든다.
   - speculative abstraction, 과한 템플릿, 미래 기능을 위한 구조를 만들지 않는다.
   - 짧고 직접적인 변경으로 해결할 수 있으면 그 방식을 우선한다.

3. Surgical Changes
   - 요청과 직접 관련된 파일만 수정한다.
   - 기존 코드와 문서의 톤, 구조, 네이밍, 링크 방식을 따른다.
   - 관련 없는 정리, 대규모 재작성, 포맷팅 churn은 요청 없이는 하지 않는다.

4. Goal-Driven Execution
   - 작업 전 성공 기준을 짧게 정한다.
   - 구현 후 테스트, 링크, 인덱스, 변경 범위를 확인한다.
   - 새 지식이나 결정이 생기면 관련 위키 페이지, `llm-wiki/index.md`, `llm-wiki/log.md`를 갱신한다.

## LLM Wiki Workflow

### Session Start

1. `llm-wiki/index.md`를 먼저 읽고 관련 페이지를 찾는다.
2. 최근 변경 맥락이 필요하면 `llm-wiki/log.md`의 마지막 항목을 확인한다.
3. 위키에 없는 내용은 코드, 원본 자료, 필요 시 `docs/`에서 확인하고 위키에 정리한다.
4. `docs/`에만 있는 내용이 AI 작업에 필요하면 `llm-wiki/`에도 반영한다.

### Ingest

1. 새 원본 자료는 `llm-wiki/raw/`에 둔다.
2. 원본은 수정하지 않는다.
3. 핵심 내용을 `llm-wiki/wiki/`의 기존 페이지에 통합하거나 새 페이지로 만든다.
4. 새 개념, 결정, 출처, 열린 질문이 생기면 적절한 하위 폴더에 문서를 만들거나 업데이트한다.
5. `llm-wiki/index.md`에 링크와 1줄 요약을 추가한다.
6. `llm-wiki/log.md`에 `## [YYYY-MM-DD] ingest | 제목` 형식으로 이력을 남긴다.

### Query

1. 답변 전 `llm-wiki/index.md`를 먼저 본다.
2. 관련 위키 문서를 읽고, 필요한 경우 코드, 원본 자료, 사람용 `docs/`로 사실을 검증한다.
3. 답변 중 보존 가치가 있는 비교, 결정, 분석은 위키 페이지로 남긴다.
4. 위키를 갱신했다면 `llm-wiki/index.md`와 `llm-wiki/log.md`도 함께 갱신한다.
5. 사람이 읽을 필요가 있는 내용이면 `docs/`에도 반영할지 판단하되, AI 작업 기준은 반드시 `llm-wiki/`에 남긴다.

### Lint

1. 깨진 링크, 고아 문서, 중복 개념, 오래된 주장, 모순을 찾는다.
2. 코드, 설정, 테스트와 충돌하는 위키 내용은 최신 기준으로 업데이트하거나 열린 질문으로 표시한다.
3. 새로 생긴 문서가 인덱스에 빠져 있으면 `llm-wiki/index.md`에 추가한다.
4. 점검 결과를 `llm-wiki/log.md`에 `## [YYYY-MM-DD] lint | 요약` 형식으로 남긴다.

## Page Rules

- 파일명은 소문자 kebab-case를 사용한다.
- 위키 페이지는 가능한 한 YAML frontmatter를 둔다.
- 관련 페이지는 Markdown 상대 링크로 연결한다.
- 확실하지 않은 내용은 단정하지 말고 `Open Questions`에 남긴다.
- 코드, 설정, 테스트가 최종 사실 기준이고, `llm-wiki/`는 AI가 작업에 쓰는 지식 레이어다.
- `docs/`는 사람 전용 문서다. `docs/`의 내용이 AI 작업에도 필요하면 `llm-wiki/`에도 둔다.

## Engineering References

- FastAPI, WebSocket 구현 전 [llm-wiki/wiki/backend-guidelines.md](/Users/723poil/Documents/git/haejillyeok/backend/llm-wiki/wiki/backend-guidelines.md)를 확인한다.
- 코드 스타일, 레이어 책임, 테스트 기준은 [llm-wiki/wiki/code-conventions.md](/Users/723poil/Documents/git/haejillyeok/backend/llm-wiki/wiki/code-conventions.md)를 따른다.
- public API 계약이 바뀌면 AI 작업 기준은 `llm-wiki/`에, 사람이 읽는 설명은 필요 시 [docs/api.md](/Users/723poil/Documents/git/haejillyeok/backend/docs/api.md)에 반영한다.
- 아키텍처 경계가 바뀌면 AI 작업 기준은 `llm-wiki/`에, 사람이 읽는 설명은 필요 시 [docs/architecture.md](/Users/723poil/Documents/git/haejillyeok/backend/docs/architecture.md)에 반영한다.

## Comment Rules

- 로직 설명과 함수 docstring은 한국어로 작성한다.
- public 함수, service/repository 메서드, WebSocket connection manager 메서드는 의도, 주요 입력, 반환값, 부작용을 설명한다.
- 복잡한 분기, 비즈니스 규칙, timeout/cancellation, transaction, retry/compensation 로직에는 왜 그렇게 처리하는지 주석을 남긴다.
- 코드가 이미 명확히 말하는 내용을 반복하는 주석은 피한다.
- 외부 계약과 연결되는 함수는 관련 API, WebSocket message type을 주석이나 docstring에 명시한다.

## Update Checklist

- 새 파일을 만들었는가?
- 관련 인덱스에 링크와 1줄 요약을 추가했는가?
- LLM Wiki를 건드렸다면 `llm-wiki/log.md`에 이력을 남겼는가?
- AI가 작업에 쓸 정보가 `docs/`에만 있고 `llm-wiki/`에 빠져 있지는 않은가?
- 코드 변경이 있었다면 적절한 테스트나 검증을 실행했는가?
- 코드, 설정, 테스트와 위키 내용이 서로 충돌하지 않는가?
