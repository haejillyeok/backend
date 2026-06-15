"""scope used words by round

Revision ID: 20260615_0009
Revises: 20260614_0008
Create Date: 2026-06-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260615_0009"
down_revision: str | None = "20260614_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORD_GAME_SCHEMA = "word_game"


def upgrade() -> None:
    """사용 단어 중복 판정을 세션 전체가 아니라 라운드 단위로 좁힙니다."""
    op.add_column(
        "used_words",
        sa.Column("round_number", sa.Integer(), nullable=True),
        schema=WORD_GAME_SCHEMA,
    )
    op.execute("UPDATE word_game.used_words SET round_number = 1")
    op.alter_column(
        "used_words",
        "round_number",
        existing_type=sa.Integer(),
        nullable=False,
        schema=WORD_GAME_SCHEMA,
    )
    op.create_check_constraint(
        "ck_used_words_round_number",
        "used_words",
        "round_number >= 1",
        schema=WORD_GAME_SCHEMA,
    )
    op.drop_constraint(
        "uq_used_words_session_word",
        "used_words",
        schema=WORD_GAME_SCHEMA,
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_used_words_session_round_word",
        "used_words",
        ["session_id", "round_number", "normalized_word"],
        schema=WORD_GAME_SCHEMA,
    )


def downgrade() -> None:
    """사용 단어 중복 판정 범위를 기존 세션 단위로 되돌립니다."""
    op.drop_constraint(
        "uq_used_words_session_round_word",
        "used_words",
        schema=WORD_GAME_SCHEMA,
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_used_words_session_word",
        "used_words",
        ["session_id", "normalized_word"],
        schema=WORD_GAME_SCHEMA,
    )
    op.drop_constraint(
        "ck_used_words_round_number",
        "used_words",
        schema=WORD_GAME_SCHEMA,
        type_="check",
    )
    op.drop_column("used_words", "round_number", schema=WORD_GAME_SCHEMA)
