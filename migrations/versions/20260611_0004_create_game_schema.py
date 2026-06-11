"""create game schema

Revision ID: 20260611_0004
Revises: 20260609_0003
Create Date: 2026-06-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260611_0004"
down_revision: str | None = "20260609_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_SCHEMA = "users"
GAME_SCHEMA = "game"
WORD_GAME_SCHEMA = "word_game"
UUID = postgresql.UUID(as_uuid=True)
JSONB_EMPTY = sa.text("'{}'::jsonb")


def upgrade() -> None:
    """게임 플랫폼과 단어 게임 확장 table을 생성합니다."""
    op.execute(sa.schema.CreateSchema(GAME_SCHEMA, if_not_exists=True))
    op.execute(sa.schema.CreateSchema(WORD_GAME_SCHEMA, if_not_exists=True))

    op.create_table(
        "rooms",
        sa.Column("id", UUID, nullable=False),
        sa.Column("public_id", UUID, nullable=False),
        sa.Column("owner_user_id", UUID, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("game_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("max_players", sa.Integer(), nullable=False),
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
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("max_players > 0", name="ck_rooms_max_players_positive"),
        sa.ForeignKeyConstraint(["owner_user_id"], [f"{USER_SCHEMA}.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_rooms_owner_user_id",
        "rooms",
        ["owner_user_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "room_members",
        sa.Column("id", UUID, nullable=False),
        sa.Column("room_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("is_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], [f"{GAME_SCHEMA}.rooms.id"]),
        sa.ForeignKeyConstraint(["user_id"], [f"{USER_SCHEMA}.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_room_members_room_id",
        "room_members",
        ["room_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_room_members_user_id",
        "room_members",
        ["user_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "uq_room_members_active_room_user",
        "room_members",
        ["room_id", "user_id"],
        unique=True,
        schema=GAME_SCHEMA,
        postgresql_where=sa.text("left_at IS NULL"),
    )

    op.create_table(
        "game_sessions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("public_id", UUID, nullable=False),
        sa.Column("room_id", UUID, nullable=False),
        sa.Column("game_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rule_config", postgresql.JSONB(), nullable=False, server_default=JSONB_EMPTY),
        sa.Column("current_phase_id", UUID, nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["room_id"], [f"{GAME_SCHEMA}.rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_game_sessions_room_id",
        "game_sessions",
        ["room_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "session_participants",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("participant_type", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("original_nickname", sa.Text(), nullable=True),
        sa.Column("seat_number", sa.Integer(), nullable=False),
        sa.Column(
            "is_uninvited_guest",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "participant_type IN ('user', 'ai')",
            name="ck_session_participants_participant_type",
        ),
        sa.CheckConstraint(
            """
            (participant_type = 'user' AND user_id IS NOT NULL)
            OR (participant_type = 'ai' AND user_id IS NULL)
            """,
            name="ck_session_participants_type_user_id",
        ),
        sa.CheckConstraint("seat_number >= 1", name="ck_session_participants_seat_number"),
        sa.ForeignKeyConstraint(["session_id"], [f"{GAME_SCHEMA}.game_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], [f"{USER_SCHEMA}.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "seat_number",
            name="uq_session_participants_session_seat",
        ),
        sa.UniqueConstraint(
            "session_id",
            "user_id",
            name="uq_session_participants_session_user",
        ),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_participants_session_id",
        "session_participants",
        ["session_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_participants_user_id",
        "session_participants",
        ["user_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "session_phases",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("phase_type", sa.Text(), nullable=False),
        sa.Column("phase_number", sa.Integer(), nullable=False),
        sa.Column("parent_phase_id", UUID, nullable=True),
        sa.Column("actor_participant_id", UUID, nullable=True),
        sa.Column(
            "condition_payload", postgresql.JSONB(), nullable=False, server_default=JSONB_EMPTY
        ),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_status", sa.Text(), nullable=True),
        sa.CheckConstraint("phase_number >= 1", name="ck_session_phases_phase_number"),
        sa.CheckConstraint(
            "time_limit_seconds IS NULL OR time_limit_seconds > 0",
            name="ck_session_phases_time_limit_seconds",
        ),
        sa.ForeignKeyConstraint(
            ["actor_participant_id"], [f"{GAME_SCHEMA}.session_participants.id"]
        ),
        sa.ForeignKeyConstraint(["parent_phase_id"], [f"{GAME_SCHEMA}.session_phases.id"]),
        sa.ForeignKeyConstraint(["session_id"], [f"{GAME_SCHEMA}.game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "phase_number", name="uq_session_phases_session_number"),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_phases_actor_participant_id",
        "session_phases",
        ["actor_participant_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_phases_parent_phase_id",
        "session_phases",
        ["parent_phase_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_phases_session_id",
        "session_phases",
        ["session_id"],
        schema=GAME_SCHEMA,
    )
    op.create_foreign_key(
        "fk_game_sessions_current_phase_id_session_phases",
        "game_sessions",
        "session_phases",
        ["current_phase_id"],
        ["id"],
        source_schema=GAME_SCHEMA,
        referent_schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_game_sessions_current_phase_id",
        "game_sessions",
        ["current_phase_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "participant_actions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("phase_id", UUID, nullable=True),
        sa.Column("participant_id", UUID, nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("action_number", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=JSONB_EMPTY),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("action_number >= 1", name="ck_participant_actions_action_number"),
        sa.CheckConstraint(
            "attempt_number IS NULL OR attempt_number >= 1",
            name="ck_participant_actions_attempt_number",
        ),
        sa.ForeignKeyConstraint(["participant_id"], [f"{GAME_SCHEMA}.session_participants.id"]),
        sa.ForeignKeyConstraint(["phase_id"], [f"{GAME_SCHEMA}.session_phases.id"]),
        sa.ForeignKeyConstraint(["session_id"], [f"{GAME_SCHEMA}.game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "action_number",
            name="uq_participant_actions_session_number",
        ),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_participant_actions_participant_id",
        "participant_actions",
        ["participant_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_participant_actions_phase_id",
        "participant_actions",
        ["phase_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_participant_actions_session_id",
        "participant_actions",
        ["session_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "state_snapshots",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("phase_id", UUID, nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("snapshot_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=JSONB_EMPTY),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_state_snapshots_sequence"),
        sa.ForeignKeyConstraint(["phase_id"], [f"{GAME_SCHEMA}.session_phases.id"]),
        sa.ForeignKeyConstraint(["session_id"], [f"{GAME_SCHEMA}.game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_state_snapshots_session_sequence"),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_state_snapshots_phase_id",
        "state_snapshots",
        ["phase_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_state_snapshots_session_id",
        "state_snapshots",
        ["session_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "game_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("phase_id", UUID, nullable=True),
        sa.Column("participant_id", UUID, nullable=True),
        sa.Column("action_id", UUID, nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=JSONB_EMPTY),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_game_events_sequence"),
        sa.ForeignKeyConstraint(["action_id"], [f"{GAME_SCHEMA}.participant_actions.id"]),
        sa.ForeignKeyConstraint(["participant_id"], [f"{GAME_SCHEMA}.session_participants.id"]),
        sa.ForeignKeyConstraint(["phase_id"], [f"{GAME_SCHEMA}.session_phases.id"]),
        sa.ForeignKeyConstraint(["session_id"], [f"{GAME_SCHEMA}.game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_game_events_session_sequence"),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_game_events_action_id",
        "game_events",
        ["action_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_game_events_participant_id",
        "game_events",
        ["participant_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_game_events_phase_id",
        "game_events",
        ["phase_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_game_events_session_id",
        "game_events",
        ["session_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "score_ledger",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("participant_id", UUID, nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", UUID, nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("score_delta", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["participant_id"], [f"{GAME_SCHEMA}.session_participants.id"]),
        sa.ForeignKeyConstraint(["session_id"], [f"{GAME_SCHEMA}.game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_score_ledger_participant_id",
        "score_ledger",
        ["participant_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_score_ledger_session_id",
        "score_ledger",
        ["session_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "votes",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("voter_participant_id", UUID, nullable=False),
        sa.Column("target_participant_id", UUID, nullable=False),
        sa.Column(
            "voted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], [f"{GAME_SCHEMA}.game_sessions.id"]),
        sa.ForeignKeyConstraint(
            ["target_participant_id"], [f"{GAME_SCHEMA}.session_participants.id"]
        ),
        sa.ForeignKeyConstraint(
            ["voter_participant_id"], [f"{GAME_SCHEMA}.session_participants.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "voter_participant_id", name="uq_votes_session_voter"),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_votes_session_id",
        "votes",
        ["session_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_votes_target_participant_id",
        "votes",
        ["target_participant_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_votes_voter_participant_id",
        "votes",
        ["voter_participant_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "session_results",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("participant_id", UUID, nullable=False),
        sa.Column("final_score", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("is_winner", sa.Boolean(), nullable=False),
        sa.Column("revealed_participant_type", sa.Text(), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False, server_default=JSONB_EMPTY),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rank >= 1", name="ck_session_results_rank"),
        sa.CheckConstraint(
            "revealed_participant_type IN ('user', 'ai')",
            name="ck_session_results_revealed_participant_type",
        ),
        sa.ForeignKeyConstraint(["participant_id"], [f"{GAME_SCHEMA}.session_participants.id"]),
        sa.ForeignKeyConstraint(["session_id"], [f"{GAME_SCHEMA}.game_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "participant_id", name="uq_session_results_session_participant"
        ),
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_results_participant_id",
        "session_results",
        ["participant_id"],
        schema=GAME_SCHEMA,
    )
    op.create_index(
        "ix_session_results_session_id",
        "session_results",
        ["session_id"],
        schema=GAME_SCHEMA,
    )

    op.create_table(
        "turns",
        sa.Column("id", UUID, nullable=False),
        sa.Column("phase_id", UUID, nullable=False),
        sa.Column("participant_id", UUID, nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column(
            "condition_payload", postgresql.JSONB(), nullable=False, server_default=JSONB_EMPTY
        ),
        sa.CheckConstraint("round_number >= 1", name="ck_turns_round_number"),
        sa.CheckConstraint("turn_number >= 1", name="ck_turns_turn_number"),
        sa.ForeignKeyConstraint(["participant_id"], [f"{GAME_SCHEMA}.session_participants.id"]),
        sa.ForeignKeyConstraint(["phase_id"], [f"{GAME_SCHEMA}.session_phases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phase_id", name="uq_turns_phase_id"),
        schema=WORD_GAME_SCHEMA,
    )
    op.create_index(
        "ix_turns_participant_id",
        "turns",
        ["participant_id"],
        schema=WORD_GAME_SCHEMA,
    )

    op.create_table(
        "submissions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("action_id", UUID, nullable=False),
        sa.Column("turn_id", UUID, nullable=False),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("normalized_word", sa.Text(), nullable=False),
        sa.Column("dictionary_payload", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["action_id"], [f"{GAME_SCHEMA}.participant_actions.id"]),
        sa.ForeignKeyConstraint(["turn_id"], [f"{WORD_GAME_SCHEMA}.turns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id", name="uq_submissions_action_id"),
        schema=WORD_GAME_SCHEMA,
    )
    op.create_index(
        "ix_submissions_turn_id",
        "submissions",
        ["turn_id"],
        schema=WORD_GAME_SCHEMA,
    )

    op.create_table(
        "used_words",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("submission_id", UUID, nullable=False),
        sa.Column("normalized_word", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], [f"{GAME_SCHEMA}.game_sessions.id"]),
        sa.ForeignKeyConstraint(["submission_id"], [f"{WORD_GAME_SCHEMA}.submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "normalized_word", name="uq_used_words_session_word"),
        sa.UniqueConstraint("submission_id", name="uq_used_words_submission_id"),
        schema=WORD_GAME_SCHEMA,
    )
    op.create_index(
        "ix_used_words_session_id",
        "used_words",
        ["session_id"],
        schema=WORD_GAME_SCHEMA,
    )


def downgrade() -> None:
    """게임 플랫폼과 단어 게임 확장 table을 삭제합니다."""
    op.drop_constraint(
        "fk_game_sessions_current_phase_id_session_phases",
        "game_sessions",
        schema=GAME_SCHEMA,
        type_="foreignkey",
    )

    op.drop_table("used_words", schema=WORD_GAME_SCHEMA)
    op.drop_table("submissions", schema=WORD_GAME_SCHEMA)
    op.drop_table("turns", schema=WORD_GAME_SCHEMA)

    op.drop_table("session_results", schema=GAME_SCHEMA)
    op.drop_table("votes", schema=GAME_SCHEMA)
    op.drop_table("score_ledger", schema=GAME_SCHEMA)
    op.drop_table("game_events", schema=GAME_SCHEMA)
    op.drop_table("state_snapshots", schema=GAME_SCHEMA)
    op.drop_table("participant_actions", schema=GAME_SCHEMA)
    op.drop_table("session_phases", schema=GAME_SCHEMA)
    op.drop_table("session_participants", schema=GAME_SCHEMA)
    op.drop_table("game_sessions", schema=GAME_SCHEMA)
    op.drop_table("room_members", schema=GAME_SCHEMA)
    op.drop_table("rooms", schema=GAME_SCHEMA)

    op.execute(sa.schema.DropSchema(WORD_GAME_SCHEMA, if_exists=True))
    op.execute(sa.schema.DropSchema(GAME_SCHEMA, if_exists=True))
