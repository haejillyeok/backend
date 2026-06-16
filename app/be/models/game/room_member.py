from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.be.models.base import Base
from app.be.models.user import USER_SCHEMA
from app.be.models.game.constants import GAME_SCHEMA
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.timezone import kst_now


class RoomMember(Base):
    """게임 시작 전에 room에 허용된 실제 유저 멤버십을 나타냅니다."""

    __tablename__ = "room_members"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    room_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.rooms.id"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{USER_SCHEMA}.users.id"),
        nullable=False,
    )
    is_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
