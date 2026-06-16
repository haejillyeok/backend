from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class AiTurnContext:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    game_type: Literal["word_chain", "chosung", "contains"]
    used_words: list[str]
    required_start_char: str | None
