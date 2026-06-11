from pydantic import AliasChoices, Field, field_validator

from app.agent.schemas.base import AgentSchemaModel


class StackOptions(AgentSchemaModel):
    overwrite_existing: bool = False
    preserve_used_count: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "preserve_used_count",
            "preserve_ai_used_count",
        ),
    )


class DataStackRequest(AgentSchemaModel):
    request_id: str | None = None
    source: str = "manual"
    words: list[str] = Field(min_length=1)
    options: StackOptions = Field(default_factory=StackOptions)

    @field_validator("words")
    @classmethod
    def reject_blank_words(cls, words: list[str]) -> list[str]:
        if any(not word or not word.strip() for word in words):
            raise ValueError("words must not contain blank values")
        return words
