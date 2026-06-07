---
title: Auth Session Login
type: decision
updated: 2026-06-05
audience: ai
---

# Auth Session Login

## Decision

PoC 인증은 `POST /api/v1/auth/login` 하나로 가입과 로그인을 함께 처리한다.
닉네임이 없으면 `users.users`에 새 유저를 만들고, 닉네임이 있으면 비밀번호를 검증한다.
성공 시 opaque session token을 `session_token` HttpOnly cookie로 발급하고, DB에는 토큰 원문이 아니라 해시를 저장한다.

## API Contract

- Method/path: `POST /api/v1/auth/login`
- Request body: `nickname`, `password`
- `nickname`은 유저 로그인 ID 역할을 한다.
- 신규 닉네임이면 가입 후 로그인 성공으로 처리한다.
- 기존 닉네임이면 `password_hash`로 비밀번호를 검증한다.
- 기존 닉네임의 비밀번호가 틀리면 `401`을 반환한다.
- 성공 response는 공통 response envelope의 `data`에 외부용 유저 식별자인 `public_id`, `nickname`, `is_new_user`, `expires_at`을 포함한다.
- 성공 response는 `session_token` cookie를 설정한다.

## Session Storage

- PostgreSQL schema: `users`
- table: `users.user_sessions`
- 내부용 관리번호: `id` UUID v7 primary key
- 유저 참조: `user_id` -> `users.users.id`
- 세션 토큰 저장값: `token_hash` `text`, unique, not null
- 부가 정보: `user_agent`, `last_access_ip`
- 시각 정보: `created_at`, `last_seen_at`, `expires_at`, `revoked_at`

## Cookie Rules

- cookie name은 `session_token`이다.
- cookie는 항상 `HttpOnly`, `SameSite=Lax`로 설정한다.
- `prod` 환경에서는 `Secure`를 켠다.
- local/dev 환경에서는 로컬 HTTP 테스트를 위해 `Secure`를 끈다.

## Rationale

- 현재 요구는 브라우저 기반 PoC 인증이므로 JWT보다 서버 저장 session token이 단순하다.
- 로그아웃, 강제 만료, WebSocket connection cleanup, 멀티 서버 공유 저장소 전환이 session table 기반에서 더 직접적이다.
- session token 원문을 DB에 저장하지 않으면 DB 노출 시 쿠키 값 재사용 위험을 낮출 수 있다.
- 멀티 서버가 되더라도 각 서버가 같은 PostgreSQL 또는 Redis session store를 조회하면 같은 cookie/session token 방식을 유지할 수 있다.

## Future Notes

- 트래픽이 커져 매 요청 DB 조회가 부담되면 Redis를 session cache로 두고 DB는 영속 기록/감사 용도로 유지한다.
- 외부 API나 모바일 등 stateless 검증 요구가 생기면 짧은 access JWT와 서버 저장 refresh/session token 조합을 검토한다.
