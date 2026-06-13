"""create valid words

Revision ID: 20260614_0008
Revises: 20260614_0007
Create Date: 2026-06-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260614_0008"
down_revision: str | None = "20260614_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORD_GAME_SCHEMA = "word_game"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    """단어 게임에서 제출 단어 유효성을 판정할 사전 table을 생성합니다."""
    op.create_table(
        "valid_words",
        sa.Column("id", UUID, nullable=False),
        sa.Column("game_type", sa.Text(), nullable=False),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("normalized_word", sa.Text(), nullable=False),
        sa.Column("starts_with", sa.Text(), nullable=False),
        sa.Column("ends_with", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("word <> ''", name="ck_valid_words_word_not_empty"),
        sa.CheckConstraint(
            "normalized_word <> ''",
            name="ck_valid_words_normalized_word_not_empty",
        ),
        sa.CheckConstraint("starts_with <> ''", name="ck_valid_words_starts_with_not_empty"),
        sa.CheckConstraint("ends_with <> ''", name="ck_valid_words_ends_with_not_empty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_type", "normalized_word", name="uq_valid_words_game_word"),
        schema=WORD_GAME_SCHEMA,
    )


def downgrade() -> None:
    """단어 게임 사전 table을 제거합니다."""
    op.drop_table("valid_words", schema=WORD_GAME_SCHEMA)
