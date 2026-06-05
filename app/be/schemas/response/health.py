from app.be.schemas.base import SchemaModel


class HealthResponse(SchemaModel):
    status: str
