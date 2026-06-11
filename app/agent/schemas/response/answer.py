from typing import Literal

from app.agent.schemas.base import AgentSchemaModel
from app.agent.schemas.request.answer import GameType


class AgentAnswerResponse(AgentSchemaModel):
    request_id: str | None
    room_id: str
    game_type: GameType
    answer: str | None
    status: Literal["ok", "no_candidate"]
    reason: str | None = None
