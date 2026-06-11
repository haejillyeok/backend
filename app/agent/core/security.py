import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from pydantic import SecretStr

from app.agent.core.config import AgentSettings


api_key_header = APIKeyHeader(
    name="X-Agent-API-Key",
    scheme_name="AgentApiKey",
    description="Backend-to-Agent shared API key.",
    auto_error=False,
)


def get_agent_settings(request: Request) -> AgentSettings:
    """현재 Agent 앱에 연결된 런타임 설정을 반환합니다."""
    return request.app.state.agent_settings


def verify_api_key(
    provided_api_key: str | None,
    configured_api_key: SecretStr | None,
) -> None:
    """요청 API 키를 상수 시간 비교로 검증합니다."""
    if configured_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent API authentication is not configured",
        )

    expected = configured_api_key.get_secret_value()
    if provided_api_key is None or not secrets.compare_digest(
        provided_api_key,
        expected,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid agent API key",
        )


async def require_agent_api_key(
    provided_api_key: Annotated[str | None, Depends(api_key_header)],
    settings: Annotated[AgentSettings, Depends(get_agent_settings)],
) -> None:
    """비즈니스 API 요청의 공유 키 인증을 강제합니다."""
    verify_api_key(provided_api_key, settings.agent_api_key)
