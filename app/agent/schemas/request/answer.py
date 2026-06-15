from enum import Enum

from pydantic import Field

from app.agent.schemas.base import AgentSchemaModel


class GameType(str, Enum):
    WORD_CHAIN = "word_chain"
    CHOSUNG = "chosung"
    CONTAINS = "contains"


class AgentCondition(AgentSchemaModel):
    last_char: str | None = None
    chosung: str | None = None
    contains_word: str | None = None


class AIPolicy(AgentSchemaModel):
    allow_fake_mistake: bool = False
    allow_reuse_word: bool = False


class AgentAnswerRequest(AgentSchemaModel):
    request_id: str | None = None
    room_id: str = Field(min_length=1)
    game_type: GameType
    used_words: list[str]
    last_char: str | None = None
    condition: AgentCondition | None = None
    ai_policy: AIPolicy = Field(default_factory=AIPolicy)
