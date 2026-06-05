from pydantic import Field

from app.be.models.user import MAX_NICKNAME_LENGTH
from app.be.schemas.base import SchemaModel


class LoginRequest(SchemaModel):
    nickname: str = Field(min_length=1, max_length=MAX_NICKNAME_LENGTH)
    password: str = Field(min_length=1)
