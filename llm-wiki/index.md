# LLM Wiki Index

이 파일은 `llm-wiki/`의 콘텐츠 카탈로그입니다. 위키를 읽거나 갱신하기 전에 먼저 확인합니다.

## Operating Files

| Page | Summary |
| --- | --- |
| [log.md](log.md) | ingest, query, lint, maintenance 작업의 시간순 이력 |

## Project Overview

| Page | Summary |
| --- | --- |
| [wiki/current-status.md](wiki/current-status.md) | 현재 backend 레포의 실행 구조, 문서 상태, 다음에 확인할 지점 |
| [wiki/project-map.md](wiki/project-map.md) | 주요 디렉터리와 소유 책임 요약 |
| [wiki/backend-guidelines.md](wiki/backend-guidelines.md) | FastAPI, WebSocket, 서버 간 HTTP client 구현 시 AI가 따라야 하는 작업 기준 |
| [wiki/runtime-configuration.md](wiki/runtime-configuration.md) | 서버 `.env`에서 관리하는 HTTP port, OpenTelemetry exporter, Docker build/push/runtime 기준 |
| [wiki/openapi-swagger.md](wiki/openapi-swagger.md) | FastAPI OpenAPI schema, Swagger UI, operation_id, metadata 관리 기준 |
| [wiki/observability-stack.md](wiki/observability-stack.md) | OpenTelemetry, Prometheus, Grafana 기반 로컬 APM 관측 스택과 metric 기준 |
| [wiki/database-migrations.md](wiki/database-migrations.md) | Alembic 기반 DB migration 형상관리와 운영 기준 |
| [wiki/database-schema-conventions.md](wiki/database-schema-conventions.md) | UUID v7, PostgreSQL text, 내부/외부 관리번호, join 기준 등 DB schema 규칙 |
| [wiki/code-conventions.md](wiki/code-conventions.md) | Python 코드 스타일, 주석/docstring, 레이어 책임, 테스트 기준 |
| [wiki/backend-guidelines-summary.md](wiki/backend-guidelines-summary.md) | FastAPI, WebSocket, 서버 간 HTTP client, 코드 컨벤션의 빠른 요약 |

## Concepts

| Page | Summary |
| --- | --- |
| [wiki/concepts/karpathy-llm-wiki.md](wiki/concepts/karpathy-llm-wiki.md) | Karpathy LLM Wiki 패턴을 이 레포에 적용하는 방식 |

## Decisions

| Page | Summary |
| --- | --- |
| [wiki/decisions/2026-06-05-llm-wiki-structure.md](wiki/decisions/2026-06-05-llm-wiki-structure.md) | LLM Wiki를 루트 `llm-wiki/`에 두고 `index.md`/`log.md`로 운영하기로 한 결정 |
| [wiki/decisions/2026-06-05-docs-vs-llm-wiki.md](wiki/decisions/2026-06-05-docs-vs-llm-wiki.md) | `docs/`는 사람 전용 문서, `llm-wiki/`는 AI 작업 지식 전체로 분리한다는 결정 |
| [wiki/decisions/2026-06-05-backend-practices.md](wiki/decisions/2026-06-05-backend-practices.md) | FastAPI/WebSocket 기준과 코드 컨벤션을 `llm-wiki`에 작업 기준으로 둔 결정. gRPC 기준은 2026-06-09 결정으로 대체됨 |
| [wiki/decisions/2026-06-05-users-table-poc.md](wiki/decisions/2026-06-05-users-table-poc.md) | PoC 유저 테이블의 UUID v7 내부/외부 관리번호, 계정 ID, 닉네임, 비밀번호 hash, 접속 IP 관리 결정 |
| [wiki/decisions/2026-06-05-auth-session-login.md](wiki/decisions/2026-06-05-auth-session-login.md) | 계정 ID 기반 가입 겸 로그인 API와 opaque session token, HttpOnly cookie 기반 인증 결정 |
| [wiki/decisions/2026-06-05-common-api-response-and-exceptions.md](wiki/decisions/2026-06-05-common-api-response-and-exceptions.md) | `app/shared/core` 공통 response envelope와 `AppException` 기반 HTTP 예외 처리 결정. gRPC status 기준은 2026-06-09 결정으로 대체됨 |
| [wiki/decisions/2026-06-05-request-audit-logging.md](wiki/decisions/2026-06-05-request-audit-logging.md) | HTTP 요청 시작, 완료, 실패를 shared 감사 로그 포맷으로 기록하는 AOP 관측 결정. gRPC 감사 기준은 2026-06-09 결정으로 대체됨 |
| [wiki/decisions/2026-06-09-remove-application-grpc.md](wiki/decisions/2026-06-09-remove-application-grpc.md) | 애플리케이션 gRPC를 제거하고 FastAPI HTTP와 OTLP HTTP만 사용하기로 한 결정 |

## Sources

| Page | Summary |
| --- | --- |
| [wiki/sources/karpathy-llm-wiki-gist.md](wiki/sources/karpathy-llm-wiki-gist.md) | Andrej Karpathy의 `llm-wiki.md` gist 요약과 이 레포 적용 포인트 |
| [wiki/sources/framework-docs-2026-06-05.md](wiki/sources/framework-docs-2026-06-05.md) | FastAPI와 gRPC 공식 문서에서 가져온 적용 기준 요약 |

## Maintenance Rules

- 새 위키 페이지를 만들면 이 인덱스에 링크와 1줄 요약을 추가한다.
- 기존 페이지의 역할이 바뀌면 요약도 같이 갱신한다.
- 답변을 시작할 때는 이 파일을 먼저 읽고 관련 페이지로 들어간다.
- 인덱스에 없는 위키 파일을 발견하면 누락으로 보고 추가한다.
