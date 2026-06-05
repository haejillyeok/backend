---
title: Project Map
type: map
updated: 2026-06-05
---

# Project Map

## Runtime

- `app/be/main.py`: 백엔드 FastAPI 앱 생성
- `app/agent/main.py`: 에이전트 FastAPI 앱 생성
- `app/main.py`: 기존 실행 경로 호환을 위한 백엔드 앱 alias

## API

- `app/be/api/`: 백엔드 REST API router와 endpoint
- `app/agent/api/`: 에이전트 REST API router와 endpoint

## gRPC

- `app/be/grpc/`: 백엔드 내부 gRPC 서버와 proto
- `app/agent/grpc/`: 에이전트 내부 gRPC 서버와 proto
- `app/shared/grpc/`: gRPC 서버 lifecycle/helper와 client helper
- `proto/`: 공통 proto 원본

## Data and Services

- `app/be/models/`: 백엔드 SQLAlchemy ORM 모델과 Alembic metadata base
- `app/be/repository/`: 백엔드 데이터 접근 계층
- `app/be/schemas/`: 백엔드 request/response schema
- `app/be/services/`: 백엔드 비즈니스 로직
- `app/agent/services/`: 에이전트 비즈니스 로직
- `app/shared/core/config/`: 앱, DB, gRPC 설정
- `migrations/`: Alembic 환경과 DB schema migration revision

## Docs and Knowledge

- `docs/`: 사람이 보는 프로젝트 문서
- `llm-wiki/`: AI가 작업할 때 사용하는 compiled knowledge
- `llm-wiki/index.md`: 위키 탐색용 인덱스
- `llm-wiki/log.md`: 위키 작업 로그
