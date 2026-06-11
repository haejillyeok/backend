from qdrant_client import models

from app.agent.core.exceptions import InvalidGameCondition
from app.agent.schemas.request.answer import AgentAnswerRequest
from app.agent.services.game_handlers.base import GameHandler
from app.agent.utils.korean import normalize_word


class ShiritoriHandler(GameHandler):
    """끝말잇기 조건을 시작 글자 payload filter로 변환합니다."""

    def get_condition(self, request: AgentAnswerRequest) -> str:
        raw_value = (
            request.condition.last_char
            if request.condition and request.condition.last_char
            else request.last_char
        )
        value = normalize_word(raw_value or "")
        if len(value) != 1:
            raise InvalidGameCondition("shiritori requires one last_char")
        return value

    def condition_filter(self, condition: str) -> models.FieldCondition:
        return models.FieldCondition(
            key="start_word",
            match=models.MatchValue(value=condition),
        )
