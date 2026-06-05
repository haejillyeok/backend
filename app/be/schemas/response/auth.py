from datetime import datetime
from uuid import UUID

from app.be.schemas.base import SchemaModel


class LoginUserResponse(SchemaModel):
    public_id: UUID
    nickname: str


class LoginResponse(SchemaModel):
    user: LoginUserResponse
    is_new_user: bool
    expires_at: datetime
