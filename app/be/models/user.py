from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.be.models.base import Base
from app.shared.core.identifiers import generate_uuid_v7


MAX_NICKNAME_LENGTH = 15
USER_SCHEMA = "users"


def utc_now() -> datetime:
    """DB 저장용 현재 UTC 시각을 반환합니다."""
    return datetime.now(UTC)


class User(Base):
    """PoC 게임 이용자를 닉네임과 비밀번호로 관리하는 ORM 모델입니다."""

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

    @validates("nickname")
    def validate_nickname(self, key: str, nickname: str) -> str:
        """닉네임은 코드 단에서 15자 이하로 제한합니다."""
        if len(nickname) > MAX_NICKNAME_LENGTH:
            raise ValueError("닉네임은 15자 이하로 입력해야 합니다.")
        return nickname
