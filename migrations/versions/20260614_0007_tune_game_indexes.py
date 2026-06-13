"""tune game indexes

Revision ID: 20260614_0007
Revises: 20260613_0006
Create Date: 2026-06-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260614_0007"
down_revision: str | None = "20260613_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GAME_SCHEMA = "game"
WORD_GAME_SCHEMA = "word_game"


def upgrade() -> None:
    """현재 로비/매치 조회 패턴에 맞춰 중복 index를 정리하고 partial index를 보강합니다."""
    op.drop_index(
        "ix_session_participants_resume_token_hash",
        table_name="session_participants",
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_participants_resume_token_hash",
        "session_participants",
        ["resume_token_hash"],
        unique=True,
        schema=GAME_SCHEMA,
        postgresql_where=sa.text("resume_token_hash IS NOT NULL"),
    )

    op.create_index(
        "ix_rooms_open_created_at_desc",
        "rooms",
        [sa.text("created_at DESC")],
        schema=GAME_SCHEMA,
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index(
        "ix_room_members_active_room_joined_at",
        "room_members",
        ["room_id", "joined_at"],
        schema=GAME_SCHEMA,
        postgresql_where=sa.text("left_at IS NULL"),
    )
    op.create_index(
        "ix_game_sessions_active_room_started_at",
        "game_sessions",
        ["room_id", sa.text("started_at DESC")],
        schema=GAME_SCHEMA,
        postgresql_where=sa.text(
            "ended_at IS NULL AND status IN ('starting', 'playing', 'voting')"
        ),
    )
    op.create_index(
        "ix_score_ledger_session_participant",
        "score_ledger",
        ["session_id", "participant_id"],
        schema=GAME_SCHEMA,
    )

    op.drop_index(
        "ix_session_participants_session_id",
        table_name="session_participants",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_session_phases_session_id",
        table_name="session_phases",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_participant_actions_session_id",
        table_name="participant_actions",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_game_events_session_id",
        table_name="game_events",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_score_ledger_session_id",
        table_name="score_ledger",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_votes_session_id",
        table_name="votes",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_session_results_session_id",
        table_name="session_results",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_used_words_session_id",
        table_name="used_words",
        schema=WORD_GAME_SCHEMA,
    )


def downgrade() -> None:
    """게임 index 구성을 이전 revision 상태로 되돌립니다."""
    op.create_index(
        "ix_used_words_session_id",
        "used_words",
        ["session_id"],
        schema=WORD_GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_results_session_id",
        "session_results",
        ["session_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_votes_session_id",
        "votes",
        ["session_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_score_ledger_session_id",
        "score_ledger",
        ["session_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_game_events_session_id",
        "game_events",
        ["session_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_participant_actions_session_id",
        "participant_actions",
        ["session_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_phases_session_id",
        "session_phases",
        ["session_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_participants_session_id",
        "session_participants",
        ["session_id"],
        schema=GAME_SCHEMA,
    )

    op.drop_index(
        "ix_score_ledger_session_participant",
        table_name="score_ledger",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_game_sessions_active_room_started_at",
        table_name="game_sessions",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_room_members_active_room_joined_at",
        table_name="room_members",
        schema=GAME_SCHEMA,
    )
    op.drop_index(
        "ix_rooms_open_created_at_desc",
        table_name="rooms",
        schema=GAME_SCHEMA,
    )

    op.drop_index(
        "ix_session_participants_resume_token_hash",
        table_name="session_participants",
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_participants_resume_token_hash",
        "session_participants",
        ["resume_token_hash"],
        schema=GAME_SCHEMA,
        postgresql_where=sa.text("resume_token_hash IS NOT NULL"),
    )
