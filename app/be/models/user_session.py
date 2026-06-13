from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.be.models.base import Base
from app.be.models.user import USER_SCHEMA
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.timezone import kst_now


SESSION_TTL = timedelta(days=7)


class UserSession(Base):
    """로그인 세션 토큰의 해시와 만료/폐기 상태를 관리하는 ORM 모델입니다."""

    __tablename__ = "user_sessions"
    __table_args__ = {"schema": USER_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{USER_SCHEMA}.users.id"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_access_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: kst_now() + SESSION_TTL,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
