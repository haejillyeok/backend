---
title: OpenAPI and Swagger
type: guide
updated: 2026-06-05
audience: ai
---

# OpenAPI and Swagger

이 레포의 FastAPI 서버는 기본적으로 OpenAPI schema와 Swagger UI를 자동 생성한다. 별도로 끄지 않으면
각 서버 실행 시 `/openapi.json`, `/docs`, `/redoc`가 제공된다.

## Source of Truth

- public HTTP API 계약의 1차 기준은 FastAPI endpoint, Pydantic request/response schema, 테스트다.
- 사람이 읽는 API 설명은 `docs/api.md`에 둔다.
- AI가 작업할 때 쓰는 운영 기준과 결정은 `llm-wiki/`에 둔다.
- DB, gRPC, WebSocket 계약과 마찬가지로 코드와 테스트가 최종 사실 기준이다.

## Endpoint Metadata Rules

- 새 public HTTP endpoint는 `response_model`과 `status_code`를 명시한다.
- Swagger 목록에서 바로 이해할 수 있도록 `summary`를 짧게 작성한다.
- OpenAPI Generator나 프론트 client 생성에 대비해 public endpoint는 `operation_id`를 명시한다.
- `operation_id`는 서버와 도메인이 드러나도록 snake_case로 쓴다.
  - 예: `be_auth_login`, `be_api_health_check`
- 주요 실패 응답은 `responses`에 status code와 description을 남긴다.
- request/response field 설명이 필요한 경우 Pydantic `Field(description=..., examples=[...])`를 사용한다.
- 내부 ORM model이나 proto message를 response model로 직접 노출하지 않는다.

## Current Exposure

- BE 서버:
  - Swagger UI: `/docs`
  - OpenAPI JSON: `/openapi.json`
  - ReDoc: `/redoc`
- Agent 서버:
  - Swagger UI: `/docs`
  - OpenAPI JSON: `/openapi.json`
  - ReDoc: `/redoc`

## OpenAPI Generator Readiness

Swagger 화면만 확인하는 목적이면 FastAPI 기본 생성과 endpoint metadata만으로 충분하다.
프론트 SDK나 typed client를 자동 생성하려면 다음 기준을 추가로 검토한다.

- `openapi.json` export 스크립트
- generated client 출력 위치와 재생성 명령
- CI에서 OpenAPI schema 변경 감지
- `operation_id` 중복 검사
- 공통 `ResponseEnvelope[T]`를 프론트에서 어떻게 unwrap할지에 대한 client wrapper 기준

## Testing

- 일반적인 Swagger 표시용 `summary`, 설명 문구, 단순 `operation_id`는 전용 테스트로 고정하지 않는다.
- API 동작, request/response shape, 인증/권한, 주요 실패 케이스는 endpoint 동작 테스트로 검증한다.
- OpenAPI schema 테스트는 프론트 SDK 자동 생성, CI schema diff, breaking change 감지처럼 schema 자체가 제품 계약이 될 때만 추가한다.

## Open Questions

- 프론트 SDK 자동 생성을 도입할지 아직 결정하지 않았다.
- 도입한다면 generator 종류, 출력 언어, 생성물 commit 여부를 별도 결정으로 남긴다.
