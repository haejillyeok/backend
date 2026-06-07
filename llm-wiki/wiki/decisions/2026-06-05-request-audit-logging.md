---
title: Request Audit Logging
type: decision
updated: 2026-06-05
audience: ai
---

# Request Audit Logging

## Decision

HTTP/gRPC 요청의 시작, 완료, 실패를 감사 로그로 남긴다. 감사 로그는 AOP 성격의 protocol adapter에서 처리하고,
endpoint, service, repository 로직에 반복해서 넣지 않는다.

## Shared Format

- 공통 이벤트 모델과 formatter는 `app/shared/core/audit.py`에 둔다.
- logger name은 `audit.request`를 사용한다.
- 로그 메시지는 안정적인 key=value 형식을 사용한다.
- 기본 필드는 `protocol`, `phase`, `service`, `operation`, `status_code`, `duration_ms`, `peer`, `error_code`다.

예시:

```text
audit protocol=http phase=completed service=haejillyeok-be operation=GET /api/v1/health status_code=200 duration_ms=12.34 peer=127.0.0.1
```

## HTTP

- FastAPI 요청 감사 로그는 `app/shared/core/http_audit.py`의 middleware가 담당한다.
- `be`, `agent` 앱 생성 시 middleware를 등록한다.
- 시작 이벤트는 request method/path를 기록한다.
- 완료 이벤트는 response status와 duration을 기록한다.
- 예외 이벤트는 `phase=failed`, `status_code=500`, exception class 이름을 `error_code`로 기록한 뒤 예외를 다시 던진다.

## gRPC

- gRPC 요청 감사 로그는 `app/shared/grpc/audit.py`의 `AuditServerInterceptor`가 담당한다.
- `be`, `agent` gRPC server factory에서 interceptor를 등록한다.
- 현재 구현은 unary-unary RPC를 감싼다.
- `AppException`이 발생하면 `grpc_status_code`와 공통 error code를 기록한 뒤 context abort로 변환한다.
- streaming RPC가 생기면 같은 공통 formatter를 사용해 RPC type별 wrapper를 확장한다.

## Privacy Rules

- request body, response body, password, session token, authorization header, cookie 값은 감사 로그에 남기지 않는다.
- 사용자 식별자가 필요해지면 내부용 DB id가 아니라 정책적으로 허용된 외부 식별자 또는 session id hash만 검토한다.
- IP/peer, method/path, RPC method, status, duration처럼 운영 감사에 필요한 metadata 중심으로 기록한다.

## Rationale

- 요청 진입/종료 로그는 cross-cutting concern이므로 endpoint나 service에 직접 넣으면 중복과 누락이 생긴다.
- shared formatter를 사용하면 HTTP와 gRPC가 같은 감사 로그 검색 패턴을 공유할 수 있다.
- payload를 제외하면 인증 정보와 개인정보가 로그에 남을 위험을 줄일 수 있다.
