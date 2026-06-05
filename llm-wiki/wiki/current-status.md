---
title: Current Status
type: overview
updated: 2026-06-05
---

# Current Status

이 레포는 하나의 Python 백엔드 저장소에서 `be` 서버와 `agent` 서버를 함께 관리한다.

## Current Shape

- `app/be/`는 백엔드 FastAPI 앱, API 라우터, dependency, repository, schema, service 계층을 가진다.
- `app/be/models/`는 백엔드 SQLAlchemy ORM 모델과 Alembic autogenerate용 metadata base를 가진다.
- `app/agent/`는 에이전트 FastAPI 앱, API 라우터, dependency, service 계층을 가진다.
- `app/shared/`는 설정, 로깅, gRPC 서버/helper, 클라이언트 기반 코드를 공유한다.
- `migrations/`는 Alembic DB schema migration 환경과 revision 파일을 관리한다.
- `docs/`는 사람이 보는 문서이며 architecture, API, development 문서가 있다.
- `llm-wiki/`는 AI가 작업할 때 사용하는 전체 지식 레이어다.

## Development Commands

- 의존성 설치: `mise run install`
- 백엔드 서버 실행: `mise run dev-be`
- 에이전트 서버 실행: `mise run dev-agent`
- proto 생성: `mise run grpc-generate`
- 테스트: `mise run test`
- migration 생성: `mise run db-revision "message"`
- migration 적용: `mise run db-upgrade-head`
- migration 대상 DB는 기본적으로 앱과 같은 `BE_DB_*` 설정을 사용한다.

## Open Questions

- 기능별 gRPC client가 생길 때 `app/shared/clients/`의 세부 구조를 어떻게 나눌지 아직 축적된 결정이 없다.
- 실제 도메인 기능이 들어오면 `be`와 `agent` 사이의 책임 경계를 위키에 계속 갱신해야 한다.
