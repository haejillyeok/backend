from typing import Annotated

from fastapi import Cookie, Depends
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.dependencies.database import get_db_session
from app.be.repository.auth import AuthRepository
from app.be.repository.game import GameRepository
from app.be.services.auth import AuthService
from app.be.services.auth import CurrentUser
from app.be.services.game import GameService
from app.shared.clients.agent import AgentClientSettings, AgentHealthClient
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


def get_auth_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthService:
    """요청 단위 DB session으로 인증 service를 생성합니다."""
    return AuthService(AuthRepository(db_session))


async def get_current_user(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    session_token: Annotated[str | None, Cookie(alias="session_token")] = None,
) -> CurrentUser:
    """session_token 쿠키를 현재 로그인 유저로 변환합니다."""
    return await auth_service.authenticate_session(session_token)


def get_game_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GameService:
    """요청 단위 DB session으로 게임 service를 생성합니다."""
    return GameService(GameRepository(db_session))


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
