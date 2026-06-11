from datetime import UTC, datetime
import re
from uuid import UUID

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.be.models.base import Base
from app.shared.core.identifiers import generate_uuid_v7


MIN_ACCOUNT_ID_LENGTH = 3
MAX_ACCOUNT_ID_LENGTH = 20
ACCOUNT_ID_PATTERN = r"^[A-Za-z0-9_]+$"
MIN_NICKNAME_LENGTH = 3
MAX_NICKNAME_LENGTH = 20
NICKNAME_PATTERN = r"^[가-힣A-Za-z0-9_]+$"
USER_SCHEMA = "users"


def utc_now() -> datetime:
    """DB 저장용 현재 UTC 시각을 반환합니다."""
    return datetime.now(UTC)


class User(Base):
    """PoC 게임 이용자를 계정 ID, 닉네임, 비밀번호로 관리하는 ORM 모델입니다."""

    __tablename__ = "users"
    __table_args__ = {"schema": USER_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    public_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        unique=True,
        default=generate_uuid_v7,
    )
    account_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nickname: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    last_access_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @validates("account_id")
    def validate_account_id(self, key: str, account_id: str) -> str:
        """계정 ID는 문자, 숫자, _만 허용하고 3~20자로 제한합니다."""
        if not MIN_ACCOUNT_ID_LENGTH <= len(account_id) <= MAX_ACCOUNT_ID_LENGTH:
            raise ValueError("계정 ID는 3자 이상 20자 이하로 입력해야 합니다.")
        if re.fullmatch(ACCOUNT_ID_PATTERN, account_id) is None:
            raise ValueError("계정 ID는 문자, 숫자, _만 입력할 수 있습니다.")
        return account_id

    @validates("nickname")
    def validate_nickname(self, key: str, nickname: str) -> str:
        """닉네임은 한글, 영어, 숫자, _만 허용하고 3~20자로 제한합니다."""
        if not MIN_NICKNAME_LENGTH <= len(nickname) <= MAX_NICKNAME_LENGTH:
            raise ValueError("닉네임은 3자 이상 20자 이하로 입력해야 합니다.")
        if re.fullmatch(NICKNAME_PATTERN, nickname) is None:
            raise ValueError("닉네임은 한글, 영어, 숫자, _만 입력할 수 있습니다.")
        return nickname
