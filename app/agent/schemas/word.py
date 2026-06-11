from typing import Any

from pydantic import ConfigDict, Field

from app.agent.schemas.base import AgentSchemaModel


class WordCandidate(AgentSchemaModel):
    model_config = ConfigDict(extra="ignore")

    word: str
    start_word: str
    end_word: str
    chosung: str
    syllables: list[str] = Field(default_factory=list)
    length: int
    used_count: int = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "WordCandidate":
        """Qdrant payload를 검증된 후보 모델로 변환합니다."""
        return cls.model_validate(payload)
