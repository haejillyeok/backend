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
    ) -> models.Filter:
        """공통 유효성 조건과 게임별 조건, 사용 단어 제외 조건을 결합합니다."""
        condition = self.get_condition(request)
        must = [
            models.FieldCondition(
                key="game_types",
                match=models.MatchValue(value=request.game_type.value),
            ),
            models.FieldCondition(
                key="is_valid",
                match=models.MatchValue(value=True),
            ),
            models.FieldCondition(
                key="is_banned",
                match=models.MatchValue(value=False),
            ),
            self.condition_filter(condition),
        ]
        must_not = []
        if normalized_used_words:
            must_not.append(
                models.FieldCondition(
                    key="word_norm",
                    match=models.MatchAny(any=sorted(normalized_used_words)),
                )
            )
        return models.Filter(must=must, must_not=must_not or None)
