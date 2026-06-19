from pydantic import Field

from app.be.models.user import (
    ACCOUNT_ID_PATTERN,
    MAX_ACCOUNT_ID_LENGTH,
    MAX_NICKNAME_LENGTH,
    MIN_ACCOUNT_ID_LENGTH,
    MIN_NICKNAME_LENGTH,
    NICKNAME_PATTERN,
)
from app.be.schemas.base import SchemaModel


MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 20
PASSWORD_PATTERN = r"^[!-~]+$"


class LoginRequest(SchemaModel):
    account_id: str = Field(
        min_length=MIN_ACCOUNT_ID_LENGTH,
        max_length=MAX_ACCOUNT_ID_LENGTH,
        pattern=ACCOUNT_ID_PATTERN,
        description="로그인에 사용할 계정 ID입니다.",
        examples=["player_001"],
    )
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        pattern=PASSWORD_PATTERN,
        description="계정 ID에 연결된 비밀번호입니다.",
        examples=["secret-password"],
    )


class SignupRequest(SchemaModel):
    account_id: str = Field(
        min_length=MIN_ACCOUNT_ID_LENGTH,
        max_length=MAX_ACCOUNT_ID_LENGTH,
        pattern=ACCOUNT_ID_PATTERN,
        description="회원가입에 사용할 계정 ID입니다.",
        examples=["player_001"],
    )
    nickname: str = Field(
        min_length=MIN_NICKNAME_LENGTH,
        max_length=MAX_NICKNAME_LENGTH,
        pattern=NICKNAME_PATTERN,
        description="게임에서 표시할 닉네임입니다.",
        examples=["초보자"],
    )
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        pattern=PASSWORD_PATTERN,
        description="계정 ID에 연결된 비밀번호입니다.",
        examples=["secret-password"],
    )
