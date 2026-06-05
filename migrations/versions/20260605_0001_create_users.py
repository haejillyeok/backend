"""create users

Revision ID: 20260605_0001
Revises:
Create Date: 2026-06-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260605_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
USER_SCHEMA = "users"


def upgrade() -> None:
    """users table을 생성합니다."""
    op.execute(sa.schema.CreateSchema(USER_SCHEMA, if_not_exists=True))
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nickname", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("last_access_ip", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("nickname"),
        schema=USER_SCHEMA,
    )


def downgrade() -> None:
    """users table을 삭제합니다."""
    op.drop_table("users", schema=USER_SCHEMA)
    op.execute(sa.schema.DropSchema(USER_SCHEMA, if_exists=True))
