---
title: Remove Application gRPC
type: decision
date: 2026-06-09
status: accepted
audience: ai
---

# Remove Application gRPC

## Decision

이 레포에서는 애플리케이션 런타임에서 gRPC를 사용하지 않는다.

- `be`와 `agent` 서버는 FastAPI HTTP 서버만 실행한다.
- 서버 간 통신이 필요하면 대상 서버의 HTTP API 계약과 기능별 client wrapper를 사용한다.
- `app/be/grpc`, `app/agent/grpc`, `app/shared/grpc`, proto 생성 태스크, `grpcio`, `grpcio-tools`, `protobuf` 의존성은 제거한다.
- OpenTelemetry exporter는 OTLP gRPC가 아니라 OTLP HTTP를 사용하고 기본 endpoint는 `http://localhost:4318`이다.
- 공통 `AppException`과 `ErrorDefinition`은 HTTP status와 WebSocket close code만 가진다.

## Rationale

현재 PoC 단계에서 gRPC 서버, proto 생성, gRPC status mapping은 운영해야 할 표면만 늘린다.
HTTP API만 남기면 실행 경로, 테스트, 문서, 의존성이 단순해지고 두 서버의 경계도 FastAPI 계약으로
일관되게 관리할 수 있다.

## Consequences

- 새 기능은 gRPC proto나 generated binding을 만들지 않는다.
- `mise run dev-be`, `mise run dev-agent`, `mise run test`는 proto 생성에 의존하지 않는다.
- 관측 스택은 Collector와 Tempo의 OTLP HTTP receiver만 사용한다.
- 이전 gRPC 중심 가이드와 결정은 이 결정으로 대체된다.
