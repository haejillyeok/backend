from qdrant_client import models

from app.agent.core.exceptions import InvalidGameCondition
from app.agent.schemas.request.answer import AgentAnswerRequest
from app.agent.services.game_handlers.base import GameHandler
from app.agent.utils.korean import normalize_word


class ChosungHandler(GameHandler):
    """초성 조건을 chosung payload filter로 변환합니다."""

    def get_condition(self, request: AgentAnswerRequest) -> str:
        value = normalize_word(
            request.condition.chosung if request.condition and request.condition.chosung else ""
        )
        if not value:
            raise InvalidGameCondition("chosung requires condition.chosung")
        return value

    def condition_filter(self, condition: str) -> models.FieldCondition:
        return models.FieldCondition(
            key="chosung",
            match=models.MatchValue(value=condition),
        )
