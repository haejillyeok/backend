---
title: Backend Guidelines Summary
type: overview
updated: 2026-06-09
source_docs:
  - backend-guidelines.md
  - code-conventions.md
---

# Backend Guidelines Summary

이 페이지는 AI가 빠르게 참고하기 위한 요약이다. 자세한 작업 기준은 `llm-wiki/wiki/backend-guidelines.md`와 `llm-wiki/wiki/code-conventions.md`를 우선한다. `docs/`는 사람 전용 문서다.

## FastAPI

- 서버별 `create_app()`과 `lifespan`을 유지한다.
- router는 `app/{server}/api/router.py`에서 `/api/v1` prefix로 묶는다.
- endpoint는 protocol/request/response 처리만 담당하고 비즈니스 로직은 service 계층으로 넘긴다.
- DB session, auth, service provider는 FastAPI dependency로 주입한다.
- public endpoint는 Swagger/OpenAPI용 `summary`, `operation_id`, 주요 실패 `responses`를 명시한다.
- public API 변경은 `docs/api.md`에 반영한다.

## Server-to-Server Communication

- 서버 간 내부 통신은 HTTP API 계약과 client wrapper로 수행한다.
- 한 서버가 다른 서버의 service/repository를 직접 import하지 않는다.
- outbound HTTP 호출에는 timeout을 명시한다.
- retry가 필요하면 멱등성과 timeout budget을 먼저 확인한다.

## WebSocket

- 사용자-facing 실시간 통신은 FastAPI WebSocket을 기본으로 한다.
- 서버 간 단순 호출은 WebSocket이 아니라 HTTP API 호출을 우선한다.
- connection manager를 endpoint에서 분리한다.
- 메시지는 `type`, `payload` 중심의 JSON envelope로 보낸다.
- disconnect cleanup, 인증 실패, 재연결 전제를 테스트한다.

## Code Conventions

- Python 3.11 이상, 타입 힌트 기본.
- API endpoint, service, repository, schema 책임을 분리한다.
- service 계층은 FastAPI 객체에 직접 의존하지 않는다.
- 로직 설명과 함수 docstring은 한국어로 작성한다.
- public 함수, service/repository 메서드, WebSocket connection manager 메서드는 의도, 입력, 반환값, 부작용을 설명한다.
- 복잡한 비즈니스 규칙, 분기, timeout/cancellation, transaction, retry/compensation에는 왜 그렇게 처리하는지 주석을 남긴다.
- AI가 작업에 사용할 수 있는 정보는 `llm-wiki/`에 유지한다.
