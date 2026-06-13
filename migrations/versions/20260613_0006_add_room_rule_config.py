"""add room rule config

Revision ID: 20260613_0006
Revises: 20260613_0005
Create Date: 2026-06-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260613_0006"
down_revision: str | None = "20260613_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GAME_SCHEMA = "game"
DEFAULT_RULE_CONFIG = sa.text("""'{"max_rounds": 8, "turn_time_seconds": 10}'::jsonb""")


def upgrade() -> None:
    """대기 room의 게임 시작 전 룰 설정 snapshot을 저장할 컬럼을 추가합니다."""
    op.add_column(
        "rooms",
        sa.Column(
            "rule_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=DEFAULT_RULE_CONFIG,
        ),
        schema=GAME_SCHEMA,
    )


def downgrade() -> None:
    """대기 room 룰 설정 컬럼을 제거합니다."""
    op.drop_column("rooms", "rule_config", schema=GAME_SCHEMA)
