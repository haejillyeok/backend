from pydantic import Field, field_validator

from app.agent.schemas.base import AgentSchemaModel
from app.agent.schemas.request.answer import GameType


class StackOptions(AgentSchemaModel):
    is_valid: bool = True
    is_banned: bool = False
    overwrite_existing: bool = False
    preserve_ai_used_count: bool = True


class DataStackRequest(AgentSchemaModel):
    request_id: str | None = None
    source: str = "manual"
    game_types: list[GameType] = Field(min_length=1)
    words: list[str] = Field(min_length=1)
    options: StackOptions = Field(default_factory=StackOptions)

    @field_validator("words")
    @classmethod
    def reject_blank_words(cls, words: list[str]) -> list[str]:
        if any(not word or not word.strip() for word in words):
            raise ValueError("words must not contain blank values")
        return words
