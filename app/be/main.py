from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.be.api.exception_handlers import register_exception_handlers
from app.be.api.endpoints.health import router as health_router
from app.be.api.router import router as api_router
from app.shared.core.config import (
    AppSettings,
    database_lifespan,
)
from app.shared.core.http_audit import add_audit_log_middleware
from app.shared.core.logging_config import configure_logging
from app.shared.core.observability import add_observability
from app.shared.core.openapi import install_openapi_schema


settings = AppSettings(app_name="haejillyeok-be")


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with database_lifespan(app):
        yield


def create_app() -> FastAPI:
    configure_logging(settings.app_name, settings.environment)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=app_lifespan,
    )
    add_observability(app, settings.app_name, settings.environment)
    add_audit_log_middleware(app, settings.app_name)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)
    install_openapi_schema(app)

    return app


app = create_app()
