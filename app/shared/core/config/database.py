from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from typing import Literal
from urllib.parse import quote

from fastapi import FastAPI
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

EnvironmentName = Literal["local", "dev", "prod"]
logger = logging.getLogger(__name__)
sql_logger = logging.getLogger(f"{__name__}.sql")


@dataclass(frozen=True)
class DatabasePoolConfig:
    # pool에 기본으로 유지할 DB 연결 수입니다.
    pool_size: int = 5
    # pool_size를 초과해 임시로 더 만들 수 있는 연결 수입니다.
    max_overflow: int = 10
    # pool에서 연결을 가져올 때 기다리는 최대 시간(초)입니다.
    pool_timeout: int = 30
    # 오래된 연결을 재생성하는 주기(초)입니다.
    pool_recycle: int = 1800
    # 연결을 사용하기 전에 살아 있는지 확인합니다.
    pool_pre_ping: bool = True


DATABASE_POOL_CONFIG = DatabasePoolConfig()


class DatabaseSettings(BaseSettings):
    environment: EnvironmentName | None = Field(default=None, validation_alias="BE_ENV")
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    name: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="BE_DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def require_environment_values(self) -> "DatabaseSettings":
        missing = []

        if self.environment is None:
            missing.append("BE_ENV")
        if not self.host:
            missing.append("BE_DB_HOST")
        if self.port is None:
            missing.append("BE_DB_PORT")
        if not self.user:
            missing.append("BE_DB_USER")
        if not self.password:
            missing.append("BE_DB_PASSWORD")
        if not self.name:
            missing.append("BE_DB_NAME")

        if missing:
            raise ValueError(
                "Missing required database environment variables: " + ", ".join(missing)
            )

        return self

    @property
    def database_url(self) -> str:
        if (
            self.host is None
            or self.port is None
            or self.user is None
            or self.password is None
            or self.name is None
        ):
            raise ValueError("Database settings are not fully configured.")

        user = quote(self.user, safe="")
        password = quote(self.password, safe="")
        name = quote(self.name, safe="")
        return f"postgresql+asyncpg://{user}:{password}@{self.host}:{self.port}/{name}"


def create_database_engine(
    settings: DatabaseSettings | None = None,
    pool_config: DatabasePoolConfig = DATABASE_POOL_CONFIG,
) -> AsyncEngine:
    db_settings = settings or DatabaseSettings()
    engine = create_async_engine(
        db_settings.database_url,
        echo=False,
        pool_pre_ping=pool_config.pool_pre_ping,
        pool_size=pool_config.pool_size,
        max_overflow=pool_config.max_overflow,
        pool_timeout=pool_config.pool_timeout,
        pool_recycle=pool_config.pool_recycle,
    )
    enable_sql_debug_logging(engine, db_settings)
    return engine


def enable_sql_debug_logging(engine: AsyncEngine, settings: DatabaseSettings) -> None:
    if settings.environment == "prod":
        return

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def log_sql_debug(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        sql_logger.debug(statement)
        if parameters:
            sql_logger.debug("parameters=%s", parameters)


def create_database_sessionmaker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_database_engine()

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database connection failed.")
        await engine.dispose()
        raise

    app.state.db_engine = engine
    app.state.db_sessionmaker = create_database_sessionmaker(engine)
    logger.info("Database connection established.")

    try:
        yield
    finally:
        await engine.dispose()
