"""add valid word payload fields

Revision ID: 20260615_0010
Revises: 20260615_0009
Create Date: 2026-06-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260615_0010"
down_revision: str | None = "20260615_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORD_GAME_SCHEMA = "word_game"


def upgrade() -> None:
    """유효 단어 사전에 JSONL payload 검색 metadata 컬럼을 추가합니다."""
    op.add_column(
        "valid_words",
        sa.Column("chosung", sa.Text(), nullable=True),
        schema=WORD_GAME_SCHEMA,
    )
    op.add_column(
        "valid_words",
        sa.Column("syllables", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=WORD_GAME_SCHEMA,
    )
    op.add_column(
        "valid_words",
        sa.Column("length", sa.Integer(), nullable=True),
        schema=WORD_GAME_SCHEMA,
    )
    op.add_column(
        "valid_words",
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        schema=WORD_GAME_SCHEMA,
    )
    op.execute(
        """
        UPDATE word_game.valid_words
        SET
            syllables = to_jsonb(regexp_split_to_array(normalized_word, '')),
            length = char_length(normalized_word)
        WHERE syllables IS NULL OR length IS NULL
        """
    )
    op.create_check_constraint(
        "ck_valid_words_chosung_not_empty",
        "valid_words",
        "chosung IS NULL OR chosung <> ''",
        schema=WORD_GAME_SCHEMA,
    )
    op.create_check_constraint(
        "ck_valid_words_length_positive",
        "valid_words",
        "length IS NULL OR length > 0",
        schema=WORD_GAME_SCHEMA,
    )
    op.create_check_constraint(
        "ck_valid_words_used_count_non_negative",
        "valid_words",
        "used_count >= 0",
        schema=WORD_GAME_SCHEMA,
    )


def downgrade() -> None:
    """유효 단어 사전의 JSONL payload metadata 컬럼을 제거합니다."""
    op.drop_constraint(
        "ck_valid_words_used_count_non_negative",
        "valid_words",
        schema=WORD_GAME_SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_valid_words_length_positive",
        "valid_words",
        schema=WORD_GAME_SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_valid_words_chosung_not_empty",
        "valid_words",
        schema=WORD_GAME_SCHEMA,
        type_="check",
    )
    op.drop_column("valid_words", "used_count", schema=WORD_GAME_SCHEMA)
    op.drop_column("valid_words", "length", schema=WORD_GAME_SCHEMA)
    op.drop_column("valid_words", "syllables", schema=WORD_GAME_SCHEMA)
    op.drop_column("valid_words", "chosung", schema=WORD_GAME_SCHEMA)
