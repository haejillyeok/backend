from abc import ABC, abstractmethod

from qdrant_client import models

from app.agent.schemas.request.answer import AgentAnswerRequest


class GameHandler(ABC):
    """game_type별 조건 검증과 Qdrant filter 생성을 정의합니다."""

    @abstractmethod
    def get_condition(self, request: AgentAnswerRequest) -> str:
        raise NotImplementedError

    @abstractmethod
    def condition_filter(self, condition: str) -> models.FieldCondition:
        raise NotImplementedError

    def build_filter(
        self,
        request: AgentAnswerRequest,
        normalized_used_words: set[str],
        *,
        condition: str | None = None,
    ) -> models.Filter:
        """게임별 조건과 사용 단어 제외 조건을 결합합니다."""
        resolved_condition = condition or self.get_condition(request)
        must = [self.condition_filter(resolved_condition)]
        must_not = []
        if normalized_used_words:
            must_not.append(
                models.FieldCondition(
                    key="word",
                    match=models.MatchAny(any=sorted(normalized_used_words)),
                )
            )
        return models.Filter(must=must, must_not=must_not or None)
