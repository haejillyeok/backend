from typing import Literal

from app.agent.schemas.base import AgentSchemaModel


class DataStackResponse(AgentSchemaModel):
    request_id: str | None
    status: Literal["accepted"] = "accepted"
    job_id: str
    received_count: int
    message: str = "word stack job accepted"
