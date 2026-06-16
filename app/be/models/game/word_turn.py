from uuid import UUID

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.be.models.base import Base
from app.be.models.game.constants import GAME_SCHEMA, WORD_GAME_SCHEMA
from app.shared.core.identifiers import generate_uuid_v7


class WordTurn(Base):
    """단어 게임의 라운드 안 개별 턴 정보를 저장하는 ORM 모델입니다."""

    __tablename__ = "turns"
    __table_args__ = {"schema": WORD_GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    phase_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_phases.id"),
        nullable=False,
    )
    participant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    condition_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
