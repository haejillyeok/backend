# API

## BE Health

서비스 상태 확인용 엔드포인트입니다.

| Method | Path | Response |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/api/v1/health` | `{"status": "ok"}` |

## Agent Health

에이전트 상태 확인용 엔드포인트입니다.

| Method | Path | Response |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/api/v1/health` | `{"status": "ok"}` |

## Internal gRPC Health

서버 간 통신용 내부 gRPC 헬스 체크 계약입니다.

| Server | Service | RPC | Request | Response |
| --- | --- | --- | --- | --- |
| `be` | `haejillyeok.be.internal.v1.InternalHealth` | `Ping` | `PingRequest(caller)` | `PingResponse(service, status)` |
| `agent` | `haejillyeok.agent.internal.v1.InternalHealth` | `Ping` | `PingRequest(caller)` | `PingResponse(service, status)` |
