---
title: PoC Users Table
type: decision
updated: 2026-06-19
audience: ai
---

# PoC Users Table

## Decision

PoC 게임 이용자는 `users` table로 관리한다. 계정 ID와 비밀번호를 인증 정보로 사용하고,
닉네임은 게임 표시명으로 분리한다. 접속 IP는 마지막 접속 IP로 기록한다.

## Schema

- PostgreSQL schema: `users`
- table: `users.users`
- 내부용 관리번호: `id` UUID v7 primary key
- 외부용 관리번호: `public_id` UUID v7 unique, not null
- 계정 ID: `account_id` `text`, unique, not null
- 닉네임: `nickname` `text`, unique, not null
- 비밀번호: `password_hash` `text`, not null
- 접속 IP: `last_access_ip` `text`, nullable
- 생성/수정 시각: `created_at`, `updated_at`

## Rules

- 계정 ID는 영어 문자, 숫자, `_`만 허용하고 3~20자만 허용한다.
- 닉네임은 한글, 영어, 숫자, `_`만 허용하고 3~20자만 허용한다.
- 비밀번호는 공백 없는 ASCII 문자, 숫자, 특수자 입력이 가능하고 6~20자만 허용한다.
- PostgreSQL column은 `varchar(15)`가 아니라 `text`를 사용하고, 길이 제한은 코드 단에서 검증한다.
- 비밀번호는 평문이나 단순 `salt + sha256`으로 저장하지 않는다.
- 표준 라이브러리의 PBKDF2-HMAC-SHA256을 사용하고, 저장 문자열에 algorithm, iteration, salt, digest를 포함한다.
- users table join과 내부 참조는 `users.id`를 기준으로 한다.
- API, URL, 외부 응답에서 유저를 식별해야 할 때는 `users.public_id`를 사용한다.
- 외부 입력으로 `public_id`를 받으면 repository에서 `id`를 조회한 뒤 내부 흐름은 `id`로 처리한다.

## Rationale

- 유저는 로그인 이후 API, URL, 외부 응답에서 식별될 가능성이 높으므로 외부용 관리번호를 둔다.
- PostgreSQL schema는 프로젝트명이 아니라 도메인 기준으로 관리하므로 유저 도메인은 `users` schema를 사용한다.
- 내부 join 기준과 외부 노출 식별자를 분리해 내부 DB 관계 변경이 외부 계약으로 새지 않게 한다.
- UUID v7은 schema convention에 맞고 시간 정렬성이 있다.
- PBKDF2-HMAC-SHA256은 raw SHA-256보다 안전하며 추가 dependency 없이 구현할 수 있다.
