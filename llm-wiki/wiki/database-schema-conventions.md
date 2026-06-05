---
title: Database Schema Conventions
type: guide
updated: 2026-06-05
audience: ai
---

# Database Schema Conventions

이 문서는 DB table, ORM 모델, migration을 만들 때 따르는 schema 규칙이다. 코드와 migration이 최종 사실 기준이고,
AI는 새 DB schema 작업 전 이 문서를 확인한다.

## Identifier Policy

### UUID

- UUID는 UUID v7을 사용한다.
- UUID v7은 시간 정렬성이 있어 PostgreSQL index locality와 정렬/조회 흐름에 유리하다는 전제로 사용한다.
- UUID 값 생성 위치는 기능 구현 시 정하되, ORM 모델과 migration에서 UUID v7 사용 의도가 드러나야 한다.

### Internal Identifier

- 내부용 관리번호는 table join과 내부 참조에 사용하는 기본 식별자다.
- 외부 노출이 필요한 관리번호와 내부 join용 관리번호를 분리한다.
- repository, service, foreign key, join 조건은 내부용 관리번호를 기준으로 한다.
- 외부 요청/응답에서 내부용 관리번호를 그대로 노출하지 않는다.

### External Identifier

- 외부용 관리번호는 API, URL, 사용자 화면, 외부 시스템 연동처럼 외부에 노출되어야 하는 경우에만 둔다.
- 모든 table에 외부용 관리번호를 기계적으로 만들지 않는다.
- 외부 노출이 필요한 aggregate, resource, 업무 객체에 한해 별도 column으로 관리한다.
- 외부용 관리번호로 join하지 않는다. 외부 입력을 받은 뒤 내부용 관리번호를 조회하고, 이후 내부 흐름은 내부용 관리번호로 처리한다.

## PostgreSQL String Types

- PostgreSQL을 사용하므로 일반 문자열은 `varchar`보다 `text`를 기본으로 사용한다.
- 명확한 DB-level 길이 제약이 필요한 경우에만 길이 제한 타입을 검토한다.
- API validation이나 업무 규칙상의 길이 제한은 우선 Pydantic schema 또는 service validation에서 표현한다.
- unique/index 대상 문자열도 특별한 이유가 없으면 `text`를 사용한다.

## PostgreSQL Domain Schemas

- PostgreSQL schema namespace는 프로젝트명이 아니라 도메인 기준으로 관리한다.
- 앱 table은 가능한 한 `public` schema에 직접 두지 않는다.
- schema 이름은 도메인 이름을 소문자 snake_case 또는 단일 소문자 단어로 쓴다.
- 예약어 또는 혼동 가능성이 큰 단수 이름은 피하고, 필요하면 복수형 도메인 이름을 사용한다.
- 유저 도메인의 PostgreSQL schema는 `users`를 사용한다.

## Relationship Rules

- foreign key와 join은 내부용 관리번호를 기준으로 설계한다.
- 외부용 관리번호는 lookup, display, external reference 용도이며 relational integrity의 기본 축으로 쓰지 않는다.
- 외부용 관리번호가 있는 table은 내부용 관리번호와 외부용 관리번호의 역할을 모델 주석 또는 가까운 문서에 구분해 남긴다.
- migration을 만들 때 외부용 관리번호의 unique/index 필요 여부를 명시적으로 판단한다.

## ORM and Migration Notes

- ORM 모델은 `app/be/models/base.py`의 `Base`를 상속한다.
- 새 ORM 모델은 Alembic autogenerate가 읽을 수 있도록 모델 import 경로에 연결한다.
- ORM 모델은 소속 도메인 PostgreSQL schema를 `__table_args__ = {"schema": "..."}`로 명시한다.
- migration은 필요한 domain schema를 `CREATE SCHEMA IF NOT EXISTS`로 먼저 만들고, table 생성 시 `schema=...`를 명시한다.
- Alembic revision 생성 후 내부용/외부용 관리번호, UUID v7, `text` type, foreign key 기준이 위 규칙과 맞는지 직접 검토한다.

## Open Questions

- `users.users` table은 내부용 관리번호로 `id` UUID v7을 사용한다.
- 다른 도메인 table의 내부용 관리번호 column 이름과 타입은 해당 table을 만들 때 확정한다.
- 외부용 관리번호의 column 이름, prefix, 발급 규칙은 실제 외부 노출 resource가 생길 때 확정한다.
