"""create user sessions

Revision ID: 20260605_0002
Revises: 20260605_0001
Create Date: 2026-06-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260605_0002"
down_revision: str | None = "20260605_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
USER_SCHEMA = "users"


def upgrade() -> None:
    """로그인 세션 table을 생성합니다."""
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("last_access_ip", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [f"{USER_SCHEMA}.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        schema=USER_SCHEMA,
    )
    op.create_index(
        "ix_user_sessions_user_id",
        "user_sessions",
        ["user_id"],
        schema=USER_SCHEMA,
    )


def downgrade() -> None:
    """로그인 세션 table을 삭제합니다."""
    op.drop_index(
        "ix_user_sessions_user_id",
        table_name="user_sessions",
        schema=USER_SCHEMA,
    )
    op.drop_table("user_sessions", schema=USER_SCHEMA)
