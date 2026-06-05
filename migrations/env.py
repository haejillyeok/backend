import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.be.models import Base
from app.shared.core.config.database import DatabaseSettings


config = context.config
target_metadata = Base.metadata


def include_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, str],
) -> bool:
    """Alembic autogenerate 대상 DB 객체를 필터링합니다."""
    return True


def get_database_url() -> str:
    """Alembic이 migration을 실행할 대상 DB URL을 결정합니다.

    기본은 앱과 같은 `.env`/환경 변수의 `BE_DB_*` 설정입니다.
    일회성으로 다른 DB에 실행해야 할 때만 Alembic `-x database_url=...`를 사용합니다.
    """
    x_arguments = context.get_x_argument(as_dictionary=True)
    explicit_database_url = x_arguments.get("database_url")

    if explicit_database_url:
        return explicit_database_url

    return DatabaseSettings().database_url


def run_migrations_offline() -> None:
    """DB 연결 없이 SQL migration 스크립트를 생성합니다."""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """동기 connection 컨텍스트에서 실제 migration을 실행합니다."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Async SQLAlchemy engine으로 DB에 연결해 migration을 실행합니다."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Alembic CLI에서 online migration을 실행합니다."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
