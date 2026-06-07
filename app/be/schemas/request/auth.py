from pydantic import Field

from app.be.models.user import MAX_NICKNAME_LENGTH
from app.be.schemas.base import SchemaModel


class LoginRequest(SchemaModel):
    nickname: str = Field(
        min_length=1,
        max_length=MAX_NICKNAME_LENGTH,
        description="가입 또는 로그인에 사용할 닉네임입니다.",
        examples=["초보자"],
    )
    password: str = Field(
        min_length=1,
        description="닉네임에 연결된 비밀번호입니다.",
        examples=["secret-password"],
    )
