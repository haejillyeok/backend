from typing import Annotated

from fastapi import Cookie, Depends
from pydantic import ValidationError
from starlette.requests import HTTPConnection

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
from app.be.services.repository_scope import build_repository_context_factory
from app.shared.clients.agent import AgentAnswerClient, AgentClientSettings, AgentHealthClient
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


def get_auth_service(connection: HTTPConnection) -> AuthService:
    """ASGI app sessionmaker로 인증 service의 repository scope를 구성합니다."""
    return AuthService(
        repository_context_factory=build_repository_context_factory(
            connection,
            AuthRepository,
        )
    )


async def get_current_user(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    session_token: Annotated[str | None, Cookie(alias="session_token")] = None,
) -> CurrentUser:
    """session_token 쿠키를 현재 로그인 유저로 변환합니다."""
    return await auth_service.authenticate_session(session_token)


def get_game_service(connection: HTTPConnection) -> GameService:
    """ASGI app sessionmaker로 게임 service의 repository scope를 구성합니다."""
    return GameService(
        repository_context_factory=build_repository_context_factory(
            connection,
            GameRepository,
        )
    )


def get_match_service(connection: HTTPConnection) -> MatchService:
    """ASGI app sessionmaker로 match snapshot service의 repository scope를 구성합니다."""
    return MatchService(
        repository_context_factory=build_repository_context_factory(
            connection,
            MatchRepository,
        )
    )


def get_match_progress_service(connection: HTTPConnection) -> MatchProgressService:
    """ASGI app sessionmaker로 match 진행 service의 repository scope를 구성합니다."""
    return MatchProgressService(
        repository_context_factory=build_repository_context_factory(
            connection,
            MatchProgressRepository,
        )
    )


def get_match_vote_service(connection: HTTPConnection) -> MatchVoteService:
    """ASGI app sessionmaker로 match 투표 service의 repository scope를 구성합니다."""
    return MatchVoteService(
        repository_context_factory=build_repository_context_factory(
            connection,
            MatchVoteRepository,
        )
    )


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
    connection: HTTPConnection,
    progress_service: Annotated[MatchProgressService, Depends(get_match_progress_service)],
    agent_answer_client: Annotated[AgentAnswerClient, Depends(get_agent_answer_client)],
) -> MatchAiTurnService:
    """AI 턴을 Agent answer API와 match 진행 service로 연결하는 service를 생성합니다."""
    return MatchAiTurnService(
        repository_context_factory=build_repository_context_factory(
            connection,
            MatchAiTurnRepository,
        ),
        agent_answer_client=agent_answer_client,
        progress_service=progress_service,
    )


def get_optional_match_ai_turn_service(
    connection: HTTPConnection,
    progress_service: Annotated[MatchProgressService, Depends(get_match_progress_service)],
) -> MatchAiTurnService | None:
    """Agent 설정이 있으면 AI 턴 service를 생성하고, 없으면 자동 AI 실행을 비활성화합니다."""
    try:
        settings = AgentClientSettings()
    except ValidationError:
        return None

    return MatchAiTurnService(
        repository_context_factory=build_repository_context_factory(
            connection,
            MatchAiTurnRepository,
        ),
        agent_answer_client=AgentAnswerClient(settings=settings),
        progress_service=progress_service,
    )
