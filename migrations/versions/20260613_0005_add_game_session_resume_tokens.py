"""add game session resume tokens

Revision ID: 20260613_0005
Revises: 20260611_0004
Create Date: 2026-06-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260613_0005"
down_revision: str | None = "20260611_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GAME_SCHEMA = "game"


def upgrade() -> None:
    """게임 참가자별 match 복구 토큰 hash와 만료 시각을 저장할 컬럼을 추가합니다."""
    op.add_column(
        "session_participants",
        sa.Column("resume_token_hash", sa.Text(), nullable=True),
        schema=GAME_SCHEMA,
    )
    op.add_column(
        "session_participants",
        sa.Column("resume_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_participants_resume_token_hash",
        "session_participants",
        ["resume_token_hash"],
        schema=GAME_SCHEMA,
        postgresql_where=sa.text("resume_token_hash IS NOT NULL"),
    )


def downgrade() -> None:
    """게임 참가자별 match 복구 토큰 저장 컬럼을 제거합니다."""
    op.drop_index(
        "ix_session_participants_resume_token_hash",
        table_name="session_participants",
        schema=GAME_SCHEMA,
    )
    op.drop_column("session_participants", "resume_token_expires_at", schema=GAME_SCHEMA)
    op.drop_column("session_participants", "resume_token_hash", schema=GAME_SCHEMA)
