from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.api.endpoints.health import router as health_router
from app.agent.api.router import router as api_router
from app.shared.core.config import AppSettings
from app.shared.core.http_audit import add_audit_log_middleware
from app.shared.core.logging_config import configure_logging
from app.shared.core.observability import add_observability


settings = AppSettings(app_name="haejillyeok-agent")


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
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
    app.include_router(health_router)
    app.include_router(api_router)

    return app


app = create_app()
