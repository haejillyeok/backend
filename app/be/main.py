from fastapi import FastAPI

from app.be.api.endpoints.health import router as health_router
from app.be.api.router import router as api_router
from app.shared.core.config import AppSettings, database_lifespan
from app.shared.core.logging_config import configure_logging


settings = AppSettings(app_name="haejillyeok-be")


def create_app() -> FastAPI:
    configure_logging(settings.app_name, settings.environment)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=database_lifespan,
    )
    app.include_router(health_router)
    app.include_router(api_router)

    return app


app = create_app()
