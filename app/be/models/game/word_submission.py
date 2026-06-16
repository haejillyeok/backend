from uuid import UUID

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.be.models.base import Base
from app.be.models.game.constants import GAME_SCHEMA, WORD_GAME_SCHEMA
from app.shared.core.identifiers import generate_uuid_v7


class WordSubmission(Base):
    """단어 게임 제출 단어와 정규화 결과를 저장하는 ORM 모델입니다."""

    __tablename__ = "submissions"
    __table_args__ = {"schema": WORD_GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    action_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.participant_actions.id"),
        nullable=False,
    )
    turn_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{WORD_GAME_SCHEMA}.turns.id"),
        nullable=False,
    )
    word: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_word: Mapped[str] = mapped_column(Text, nullable=False)
    dictionary_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
