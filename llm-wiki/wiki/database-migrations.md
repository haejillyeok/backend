---
title: Database Migrations
type: guide
updated: 2026-06-05
audience: ai
---

# Database Migrations

이 레포의 DB schema migration은 Alembic으로 관리한다. FastAPI 앱 시작 시 table을 자동 생성하거나
migration을 자동 실행하지 않는다. Schema 변경은 코드 변경과 migration revision을 함께 Git에 커밋하고,
배포 절차에서 앱 실행 전에 migration을 적용한다.

## Ownership

- `migrations/`: Alembic 환경과 revision 파일을 둔다.
- `alembic.ini`: Alembic CLI가 읽는 프로젝트 설정이다. `script_location = migrations`만 유지하고 앱 로깅과 겹치지 않도록 logger 설정은 두지 않는다.
- `migrations/env.py`: Alembic 실행 환경이다. 대상 DB URL을 결정하고 `app.be.models.Base.metadata`를 Alembic에 연결한다.
- `migrations/script.py.mako`: 새 revision 파일을 만들 때 Alembic이 사용하는 템플릿이다.
- `migrations/versions/`: Git으로 관리하는 revision 파일을 둔다.
- `app/be/models/base.py`: `be` 서버 ORM 모델이 상속하는 SQLAlchemy `DeclarativeBase`를 둔다.
- `app/shared/core/config/database.py`: DB URL과 async engine 설정의 최종 기준이다.

`agent` 서버는 현재 DB 연결을 갖지 않는다. 새 DB schema가 필요하면 기본 소유자는 `be` 서버이고,
ORM 모델은 `app/be/models/`에 둔다.

## Workflow

1. ORM 모델을 `app/be/models/`에 추가하거나 변경한다.
2. Schema 규칙은 [database-schema-conventions.md](database-schema-conventions.md)를 따른다.
3. Alembic autogenerate가 모델 metadata를 볼 수 있도록 `migrations/env.py`에서 모델 모듈을 import한다.
4. Local DB와 `.env`를 준비한 뒤 revision을 생성한다.

```bash
mise run db-revision "change description"
```

5. 생성된 `migrations/versions/*.py`를 직접 검토한다. Autogenerate 결과를 그대로 신뢰하지 않는다.
6. Local DB에 적용해 검증한다.

```bash
mise run db-upgrade-head
mise run db-current
```

7. 모델 변경, migration revision, 관련 테스트/문서를 같은 변경 묶음으로 커밋한다.

## Runtime Rules

- 앱 lifespan에서 migration을 실행하지 않는다.
- 운영 배포에서는 앱 프로세스를 띄우기 전에 단일 migration step으로 `mise run db-upgrade-head`를 실행한다.
- 여러 앱 인스턴스가 동시에 migration을 실행하지 않게 한다.
- rollback이 필요할 수 있는 변경은 `downgrade()`를 의미 있게 작성한다. 되돌릴 수 없는 변경이면 주석으로 이유를 남긴다.
- column rename, type change, data backfill처럼 데이터 손실 가능성이 있는 변경은 autogenerate 결과를 수동으로 고친다.
- UUID v7, PostgreSQL `text`, 내부/외부 관리번호, join 기준은 [database-schema-conventions.md](database-schema-conventions.md)를 따른다.

## Target DB

기본 migration 대상 DB는 `.env` 또는 환경 변수의 `BE_DB_*` 값으로 `DatabaseSettings`가 조립한 URL이다.
Migration 전용 환경 변수는 추가로 관리하지 않는다. 특정 DB를 명시해야 하는 일회성 작업에서는
Alembic CLI `-x database_url=...`를 사용한다.

- 기본: `.env`/환경 변수의 `BE_DB_*`
- 일회성 override: Alembic CLI `-x database_url=...`

```bash
.venv/bin/python -m alembic -x database_url="postgresql+asyncpg://user:password@localhost:5432/db" upgrade head
```

## Commands

```bash
mise run db-history
mise run db-current
mise run db-revision "change description"
mise run db-upgrade head
mise run db-upgrade-head
mise run db-downgrade -1
mise run db-downgrade-one
```

## Open Questions

- 배포 도구가 정해지면 migration step을 어느 job 또는 entrypoint에 둘지 결정해야 한다.
- 실제 도메인 모델이 생기면 `migrations/env.py`의 모델 import 방식을 패키지 import 또는 명시 import 중 하나로 고정해야 한다.
