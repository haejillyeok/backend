from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.be.api.exception_handlers import register_exception_handlers
from app.be.api.endpoints.health import router as health_router
from app.be.api.router import router as api_router
from app.shared.core.config import (
    AppSettings,
    configure_app_timezone,
    database_lifespan,
)
from app.shared.core.cors import add_cors_middleware
from app.shared.core.http_audit import add_audit_log_middleware
from app.shared.core.logging_config import configure_logging
from app.shared.core.observability import add_observability
from app.shared.core.openapi import install_openapi_schema


settings = AppSettings(app_name="haejillyeok-be")
API_DESCRIPTION = """
Haejillyeok BE HTTP API입니다.

WebSocket API는 Swagger/OpenAPI에 자동 포함되지 않으므로 별도 문서 페이지에서 관리합니다.

- [WebSocket API 문서](/api/v1/ws-docs)
"""


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with database_lifespan(app):
        yield


def create_app() -> FastAPI:
    configure_app_timezone(settings.timezone)
    configure_logging(settings.app_name, settings.environment)

    app = FastAPI(
        title=settings.app_name,
        description=API_DESCRIPTION,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=app_lifespan,
    )
    add_observability(app, settings.app_name, settings.environment)
    add_audit_log_middleware(app, settings.app_name)
    add_cors_middleware(app)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)
    install_openapi_schema(app)

    return app


app = create_app()
