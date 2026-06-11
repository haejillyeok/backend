from typing import Annotated

from fastapi import Depends
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.dependencies.database import get_db_session
from app.be.repository.auth import AuthRepository
from app.be.services.auth import AuthService
from app.shared.clients.agent import AgentClientSettings, AgentHealthClient
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


def get_auth_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthService:
    """요청 단위 DB session으로 인증 service를 생성합니다."""
    return AuthService(AuthRepository(db_session))


def get_agent_health_client() -> AgentHealthClient:
    """환경변수 기반 설정으로 Agent health 전용 client를 생성합니다."""
    try:
        settings = AgentClientSettings()
    except ValidationError as exc:
        raise AppException(
            code=ErrorCode.AGENT_CLIENT_NOT_CONFIGURED,
            details={"fields": [error["loc"][0] for error in exc.errors()]},
        ) from exc

    return AgentHealthClient(settings=settings)
