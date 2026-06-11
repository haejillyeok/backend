from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agent.api.endpoints.health import router as health_router
from app.agent.api.router import router as api_router
from app.agent.core.config import AgentSettings
from app.agent.core.exceptions import InvalidGameCondition
from app.agent.dependencies.container import AgentServiceContainer
from app.shared.core.config import AppSettings, configure_app_timezone
from app.shared.core.http_audit import add_audit_log_middleware
from app.shared.core.logging_config import configure_logging
from app.shared.core.observability import add_observability
from app.shared.core.route_guard import add_registered_route_guard_middleware


settings = AppSettings(app_name="haejillyeok-agent")


def create_app(agent_settings: AgentSettings | None = None) -> FastAPI:
    resolved_agent_settings = agent_settings or AgentSettings()

    @asynccontextmanager
    async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.agent_settings = resolved_agent_settings
        app.state.agent_services = AgentServiceContainer.build(resolved_agent_settings)
        try:
            yield
        finally:
            await app.state.agent_services.close()

    configure_app_timezone(settings.timezone)
    configure_logging(settings.app_name, settings.environment)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=app_lifespan,
        docs_url="/docs" if resolved_agent_settings.expose_docs else None,
        redoc_url="/redoc" if resolved_agent_settings.expose_docs else None,
        openapi_url="/openapi.json" if resolved_agent_settings.expose_docs else None,
    )
    add_observability(app, settings.app_name, settings.environment)
    add_audit_log_middleware(app, settings.app_name)
    app.include_router(health_router)
    app.include_router(api_router)
    add_registered_route_guard_middleware(app)

    @app.exception_handler(InvalidGameCondition)
    async def invalid_game_condition_handler(
        request: Request,
        exc: InvalidGameCondition,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc)},
        )

    return app


app = create_app()
