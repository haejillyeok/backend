from pydantic import BaseModel, ConfigDict


class AgentSchemaModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
