"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """DB schema를 다음 revision으로 올립니다."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """DB schema를 이전 revision으로 되돌립니다."""
    ${downgrades if downgrades else "pass"}
