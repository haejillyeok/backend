from qdrant_client import models

from app.agent.core.exceptions import InvalidGameCondition
from app.agent.schemas.request.answer import AgentAnswerRequest
from app.agent.services.game_handlers.base import GameHandler
from app.agent.utils.korean import normalize_word


class ContainsHandler(GameHandler):
    """포함 글자 조건을 syllables payload filter로 변환합니다."""

    def get_condition(self, request: AgentAnswerRequest) -> str:
        value = normalize_word(
            request.condition.contains_word
            if request.condition and request.condition.contains_word
            else ""
        )
        if len(value) != 1:
            raise InvalidGameCondition("contains requires one condition.contains_word syllable")
        return value

    def condition_filter(self, condition: str) -> models.FieldCondition:
        return models.FieldCondition(
            key="syllables",
            match=models.MatchValue(value=condition),
        )
