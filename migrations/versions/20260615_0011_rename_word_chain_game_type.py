"""rename word chain game type

Revision ID: 20260615_0011
Revises: 20260615_0010
Create Date: 2026-06-15
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260615_0011"
down_revision: str | None = "20260615_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """저장된 끝말잇기 game_type 값을 공개 계약인 word_chain으로 바꿉니다."""
    op.execute("UPDATE game.rooms SET game_type = 'word_chain' WHERE game_type = 'shiritori'")
    op.execute(
        "UPDATE game.game_sessions SET game_type = 'word_chain' WHERE game_type = 'shiritori'"
    )
    op.execute(
        "UPDATE word_game.valid_words SET game_type = 'word_chain' WHERE game_type = 'shiritori'"
    )


def downgrade() -> None:
    """word_chain game_type 저장값을 이전 식별자인 shiritori로 되돌립니다."""
    op.execute(
        "UPDATE word_game.valid_words SET game_type = 'shiritori' WHERE game_type = 'word_chain'"
    )
    op.execute(
        "UPDATE game.game_sessions SET game_type = 'shiritori' WHERE game_type = 'word_chain'"
    )
    op.execute("UPDATE game.rooms SET game_type = 'shiritori' WHERE game_type = 'word_chain'")
