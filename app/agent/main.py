from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.api.endpoints.health import router as health_router
from app.agent.api.router import router as api_router
from app.agent.grpc.server import create_grpc_server
from app.shared.core.config import AppSettings, GrpcSettings
from app.shared.core.logging_config import configure_logging
from app.shared.grpc import grpc_server_lifespan


settings = AppSettings(app_name="haejillyeok-agent")


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    grpc_settings = GrpcSettings.from_app_name(settings.app_name)

    async with grpc_server_lifespan(
        app,
        create_grpc_server,
        grpc_settings.bind_address,
    ):
        yield


def create_app() -> FastAPI:
    configure_logging(settings.app_name, settings.environment)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=app_lifespan,
    )
    app.include_router(health_router)
    app.include_router(api_router)

    return app


app = create_app()
