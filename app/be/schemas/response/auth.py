from datetime import datetime
from uuid import UUID

from app.be.schemas.base import SchemaModel


class AuthUserResponse(SchemaModel):
    public_id: UUID
    account_id: str
    nickname: str


class LoginResponse(SchemaModel):
    user: AuthUserResponse
    expires_at: datetime


class SignupResponse(SchemaModel):
    user: AuthUserResponse
    expires_at: datetime
