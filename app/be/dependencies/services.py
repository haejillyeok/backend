from typing import Annotated

from fastapi import Cookie, Depends
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.dependencies.database import get_db_session
from app.be.repository.auth import AuthRepository
from app.be.repository.game import GameRepository
from app.be.repository.match_ai import MatchAiTurnRepository
from app.be.repository.match import MatchRepository
from app.be.repository.match_progress import MatchProgressRepository
from app.be.repository.match_vote import MatchVoteRepository
from app.be.services.auth import AuthService
from app.be.services.auth import CurrentUser
from app.be.services.game import GameService
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.be.services.match import MatchService
from app.be.services.match_vote import MatchVoteService
from app.shared.clients.agent import AgentAnswerClient, AgentClientSettings, AgentHealthClient
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


def get_match_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MatchService:
    """match WebSocket snapshot service를 생성합니다."""
    return MatchService(MatchRepository(db_session))


def get_match_progress_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MatchProgressService:
    """match 진행 상태 변경 service를 생성합니다."""
    return MatchProgressService(MatchProgressRepository(db_session))


def get_match_vote_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MatchVoteService:
    """match 투표 제출과 결과 확정 service를 생성합니다."""
    return MatchVoteService(MatchVoteRepository(db_session))


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


def get_agent_answer_client() -> AgentAnswerClient:
    """환경변수 기반 설정으로 Agent 단어 응답 client를 생성합니다."""
    try:
        settings = AgentClientSettings()
    except ValidationError as exc:
        raise AppException(
            code=ErrorCode.AGENT_CLIENT_NOT_CONFIGURED,
            details={"fields": [error["loc"][0] for error in exc.errors()]},
        ) from exc

    return AgentAnswerClient(settings=settings)


def get_match_ai_turn_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    progress_service: Annotated[MatchProgressService, Depends(get_match_progress_service)],
    agent_answer_client: Annotated[AgentAnswerClient, Depends(get_agent_answer_client)],
) -> MatchAiTurnService:
    """AI 턴을 Agent answer API와 match 진행 service로 연결하는 service를 생성합니다."""
    return MatchAiTurnService(
        MatchAiTurnRepository(db_session),
        agent_answer_client,
        progress_service,
    )


def get_optional_match_ai_turn_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    progress_service: Annotated[MatchProgressService, Depends(get_match_progress_service)],
) -> MatchAiTurnService | None:
    """Agent 설정이 있으면 AI 턴 service를 생성하고, 없으면 자동 AI 실행을 비활성화합니다."""
    try:
        settings = AgentClientSettings()
    except ValidationError:
        return None

    return MatchAiTurnService(
        MatchAiTurnRepository(db_session),
        AgentAnswerClient(settings=settings),
        progress_service,
    )
