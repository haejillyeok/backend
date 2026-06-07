---
title: Framework Docs 2026-06-05
type: source-summary
updated: 2026-06-05
---

# Framework Docs 2026-06-05

## Sources

- FastAPI Bigger Applications: <https://fastapi.tiangolo.com/tutorial/bigger-applications/>
- FastAPI Dependencies: <https://fastapi.tiangolo.com/tutorial/dependencies/>
- FastAPI Lifespan Events: <https://fastapi.tiangolo.com/advanced/events/>
- FastAPI WebSockets: <https://fastapi.tiangolo.com/advanced/websockets/>
- FastAPI Testing WebSockets: <https://fastapi.tiangolo.com/advanced/testing-websockets/>
- gRPC Deadlines: <https://grpc.io/docs/guides/deadlines/>
- gRPC Status Codes: <https://grpc.io/docs/guides/status-codes/>
- gRPC Health Checking: <https://grpc.io/docs/guides/health-checking/>
- gRPC Performance Best Practices: <https://grpc.io/docs/guides/performance/>

## Extracted Rules

- FastAPI large apps should be split into packages/modules and composed with `APIRouter`.
- FastAPI dependencies are the standard way to provide request-scoped values and shared checks.
- FastAPI lifespan should own startup/shutdown resources.
- FastAPI WebSocket endpoints support dependency usage and should be tested explicitly.
- gRPC clients should set realistic deadlines instead of waiting forever.
- gRPC status codes should communicate the actual failure category.
- gRPC health checking is a standard service pattern for server health and client routing.
- gRPC Python streaming can have performance trade-offs, so unary calls stay the default unless streaming semantics are needed.
