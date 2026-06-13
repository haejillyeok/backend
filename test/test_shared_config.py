import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.shared.core.config.database import (
    DatabasePoolConfig,
    DatabaseSettings,
    create_database_engine,
    database_lifespan,
)
from app.shared.core.config.endpoint import (
    EndpointSettings,
    format_service_env_prefix,
    load_endpoint_port_value,
)
from app.shared.core.config.http import HttpSettings, format_http_env_prefix


def test_database_settings_builds_quoted_asyncpg_url() -> None:
    settings = DatabaseSettings(
        environment="local",
        host="localhost",
        port=5432,
        user="user name",
        password="p@ ss",
        name="game db",
    )

    assert (
        settings.database_url
        == "postgresql+asyncpg://user%20name:p%40%20ss@localhost:5432/game%20db"
    )


def test_database_settings_requires_environment_values() -> None:
    with pytest.raises(ValidationError) as error:
        DatabaseSettings(_env_file=None)

    assert "Missing required database environment variables" in str(error.value)


def test_database_url_rejects_incomplete_constructed_settings() -> None:
    settings = DatabaseSettings.model_construct(environment="local")

    with pytest.raises(ValueError, match="not fully configured"):
        _ = settings.database_url


def test_create_database_engine_applies_pool_config(monkeypatch) -> None:
    created = {}

    def fake_create_async_engine(database_url, **kwargs):
        created["database_url"] = database_url
        created["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(
        "app.shared.core.config.database.create_async_engine",
        fake_create_async_engine,
    )
    monkeypatch.setattr(
        "app.shared.core.config.database.enable_sql_debug_logging",
        lambda engine, settings: created.setdefault("debug_enabled", True),
    )

    engine = create_database_engine(
        DatabaseSettings(
            environment="local",
            host="localhost",
            port=5432,
            user="user",
            password="password",
            name="haejillyeok",
        ),
        DatabasePoolConfig(
            pool_size=2,
            max_overflow=3,
            pool_timeout=4,
            pool_recycle=5,
            pool_pre_ping=False,
        ),
    )

    assert engine is not None
    assert (
        created["database_url"] == "postgresql+asyncpg://user:password@localhost:5432/haejillyeok"
    )
    assert created["kwargs"] == {
        "echo": False,
        "pool_pre_ping": False,
        "pool_size": 2,
        "max_overflow": 3,
        "pool_timeout": 4,
        "pool_recycle": 5,
    }
    assert created["debug_enabled"] is True


async def test_database_lifespan_sets_sessionmaker_and_disposes_engine(monkeypatch) -> None:
    events = []

    class FakeConnection:
        async def __aenter__(self):
            events.append("connect")
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            events.append("disconnect")

        async def execute(self, statement):
            events.append(str(statement))

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        async def dispose(self):
            events.append("dispose")

    monkeypatch.setattr("app.shared.core.config.database.create_database_engine", FakeEngine)
    monkeypatch.setattr(
        "app.shared.core.config.database.create_database_sessionmaker",
        lambda engine: "sessionmaker",
    )
    app = FastAPI()

    async with database_lifespan(app):
        assert app.state.db_sessionmaker == "sessionmaker"

    assert events == ["connect", "SELECT 1", "disconnect", "dispose"]


async def test_database_lifespan_disposes_engine_on_connection_failure(monkeypatch) -> None:
    events = []

    class FakeConnection:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, exc_type, exc, traceback):
            raise AssertionError("enter 실패 시 exit는 호출되지 않습니다.")

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        async def dispose(self):
            events.append("dispose")

    monkeypatch.setattr("app.shared.core.config.database.create_database_engine", FakeEngine)

    with pytest.raises(RuntimeError, match="db down"):
        async with database_lifespan(FastAPI()):
            pass

    assert events == ["dispose"]


def test_endpoint_settings_resolve_prefix_port_and_bind_address(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("BE_HTTP_PORT=8100\n", encoding="utf-8")
    monkeypatch.delenv("BE_HTTP_PORT", raising=False)

    settings = EndpointSettings(app_name="haejillyeok-be", host="127.0.0.1", port=8000)

    assert settings.bind_address == "127.0.0.1:8000"
    assert format_service_env_prefix("haejillyeok-be") == "BE"
    assert format_http_env_prefix("haejillyeok-be") == "BE_HTTP"
    assert load_endpoint_port_value("BE_HTTP", env_file) == "8100"
    assert HttpSettings.from_app_name("haejillyeok-agent", env_file).port == 8001


def test_load_endpoint_port_value_prefers_os_env_and_requires_value(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("BE_HTTP_PORT=8100\n", encoding="utf-8")
    monkeypatch.setenv("BE_HTTP_PORT", "8200")

    assert load_endpoint_port_value("BE_HTTP", env_file) == "8200"
    assert load_endpoint_port_value("UNKNOWN", env_file, default_port=9000) == "9000"

    with pytest.raises(ValueError, match="UNKNOWN_PORT"):
        load_endpoint_port_value("UNKNOWN", env_file)
