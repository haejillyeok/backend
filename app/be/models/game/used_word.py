from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.be.models.base import Base
from app.be.models.game.constants import GAME_SCHEMA, WORD_GAME_SCHEMA
from app.shared.core.identifiers import generate_uuid_v7


class UsedWord(Base):
    """세션의 특정 라운드 안에서 이미 사용된 단어를 중복 방지용으로 저장하는 ORM 모델입니다."""

    __tablename__ = "used_words"
    __table_args__ = {"schema": WORD_GAME_SCHEMA}

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
    submission_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{WORD_GAME_SCHEMA}.submissions.id"),
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_word: Mapped[str] = mapped_column(Text, nullable=False)
