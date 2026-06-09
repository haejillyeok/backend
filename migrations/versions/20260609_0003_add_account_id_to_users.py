"""add account id to users

Revision ID: 20260609_0003
Revises: 20260605_0002
Create Date: 2026-06-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260609_0003"
down_revision: str | None = "20260605_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
USER_SCHEMA = "users"


def upgrade() -> None:
    """users table에 로그인용 계정 ID를 추가합니다."""
    op.add_column(
        "users",
        sa.Column("account_id", sa.Text(), nullable=True),
        schema=USER_SCHEMA,
    )
    op.execute(
        sa.text(
            """
            UPDATE users.users
            SET account_id = 'user_' || substring(replace(id::text, '-', '') from 1 for 15)
            WHERE account_id IS NULL
            """
        )
    )
    op.alter_column(
        "users",
        "account_id",
        nullable=False,
        schema=USER_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_users_account_id",
        "users",
        ["account_id"],
        schema=USER_SCHEMA,
    )


def downgrade() -> None:
    """users table에서 로그인용 계정 ID를 제거합니다."""
    op.drop_constraint(
        "uq_users_account_id",
        "users",
        schema=USER_SCHEMA,
        type_="unique",
    )
    op.drop_column("users", "account_id", schema=USER_SCHEMA)
