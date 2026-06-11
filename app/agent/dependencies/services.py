"""Agent service dependency providers."""

from fastapi import Request

from app.agent.services.answer import AgentService
from app.agent.services.stack import StackService


def get_agent_service(request: Request) -> AgentService:
    """현재 요청 앱의 답변 생성 서비스를 반환합니다."""
    return request.app.state.agent_services.agent_service


def get_stack_service(request: Request) -> StackService:
    """현재 요청 앱의 단어 적재 서비스를 반환합니다."""
    return request.app.state.agent_services.stack_service
