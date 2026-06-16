from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.be.models.base import Base
from app.be.models.game.constants import GAME_SCHEMA
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.timezone import kst_now


class Vote(Base):
    """게임 종료 후 AI 손님 지목 투표를 저장하는 ORM 모델입니다."""

    __tablename__ = "votes"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    voter_participant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=False,
    )
    target_participant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=False,
    )
    voted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
