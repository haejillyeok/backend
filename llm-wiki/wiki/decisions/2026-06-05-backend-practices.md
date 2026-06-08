---
title: Backend Practices Documentation
type: decision
date: 2026-06-05
status: accepted
superseded_by: 2026-06-09-remove-application-grpc
---

# Backend Practices Documentation

## Decision

FastAPI, WebSocket 적용 기준과 Python 코드 컨벤션을 `llm-wiki/`에 AI 작업 기준으로 정리한다. 사람이 보는 버전은 `docs/`에도 둔다.

- `llm-wiki/wiki/backend-guidelines.md`: FastAPI, WebSocket, 서버 간 HTTP client 작업 기준
- `llm-wiki/wiki/code-conventions.md`: Python 코드 스타일, 레이어 책임, 테스트 기준
- `llm-wiki/wiki/backend-guidelines-summary.md`: 빠른 압축 요약
- `docs/backend-guidelines.md`: 사람이 보는 FastAPI, WebSocket 설명
- `docs/code-conventions.md`: 사람이 보는 코드 컨벤션 설명

## Rationale

이 레포는 `be`와 `agent` 서버를 함께 관리하고, REST API와 향후 실시간 소켓 통신을 사용할 예정이다. 프레임워크 사용 기준을 먼저 합의하면 기능 추가 시 구조가 흔들리지 않는다.

## Consequences

- FastAPI 기능 추가 전 `llm-wiki/wiki/backend-guidelines.md`를 확인한다.
- WebSocket 기능 추가 전 connection manager, envelope, reconnect, cleanup 테스트 기준을 확인한다.
- 코드 변경 시 `llm-wiki/wiki/code-conventions.md`의 레이어 책임을 따른다.
