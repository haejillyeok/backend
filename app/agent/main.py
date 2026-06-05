from fastapi import FastAPI

from app.agent.api.endpoints.health import router as health_router
from app.agent.api.router import router as api_router
from app.shared.core.config import AppSettings
from app.shared.core.logging_config import configure_logging


settings = AppSettings(app_name="haejillyeok-agent")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )
    app.include_router(health_router)
    app.include_router(api_router)

    return app


app = create_app()
