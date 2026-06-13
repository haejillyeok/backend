from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.be.models.base import Base
from app.be.models.user import USER_SCHEMA
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.timezone import kst_now


GAME_SCHEMA = "game"
WORD_GAME_SCHEMA = "word_game"


class Room(Base):
    """로비에서 보이는 대기방과 게임 시작 전 멤버십의 기준 ORM 모델입니다."""

    __tablename__ = "rooms"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    public_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        unique=True,
        default=generate_uuid_v7,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{USER_SCHEMA}.users.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    game_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    max_players: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
        onupdate=kst_now,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoomMember(Base):
    """게임 시작 전에 room에 허용된 실제 유저 멤버십을 나타냅니다."""

    __tablename__ = "room_members"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    room_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.rooms.id"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{USER_SCHEMA}.users.id"),
        nullable=False,
    )
    is_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GameSession(Base):
    """room에서 시작되어 match 진입 권한을 제공하는 게임 세션 ORM 모델입니다."""

    __tablename__ = "game_sessions"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    public_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        unique=True,
        default=generate_uuid_v7,
    )
    room_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.rooms.id"),
        nullable=False,
    )
    game_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    rule_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    current_phase_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
        onupdate=kst_now,
    )


class SessionParticipant(Base):
    """게임 시작 시 확정된 실제 유저 또는 AI 참가자 snapshot ORM 모델입니다."""

    __tablename__ = "session_participants"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{USER_SCHEMA}.users.id"),
        nullable=True,
    )
    participant_type: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    original_nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_uninvited_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resume_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionPhase(Base):
    """게임 세션 안의 라운드, 턴, 투표 구간 같은 진행 phase ORM 모델입니다."""

    __tablename__ = "session_phases"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    phase_type: Mapped[str] = mapped_column(Text, nullable=False)
    phase_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_phase_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_phases.id"),
        nullable=True,
    )
    actor_participant_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=True,
    )
    condition_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_status: Mapped[str | None] = mapped_column(Text, nullable=True)


class ParticipantAction(Base):
    """참가자가 phase 안에서 수행한 제출, 투표, timeout 같은 행동 ORM 모델입니다."""

    __tablename__ = "participant_actions"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    phase_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_phases.id"),
        nullable=True,
    )
    participant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    action_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class StateSnapshot(Base):
    """재접속과 화면 복구를 위해 저장하는 match 상태 snapshot ORM 모델입니다."""

    __tablename__ = "state_snapshots"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    phase_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_phases.id"),
        nullable=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class GameEvent(Base):
    """서버가 확정한 진행 event를 감사와 재전송 기준으로 저장하는 ORM 모델입니다."""

    __tablename__ = "game_events"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    phase_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_phases.id"),
        nullable=True,
    )
    participant_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=True,
    )
    action_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.participant_actions.id"),
        nullable=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class ScoreLedger(Base):
    """점수 변화 사유와 값을 원장 형태로 저장하는 ORM 모델입니다."""

    __tablename__ = "score_ledger"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    participant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    score_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class Vote(Base):
    """게임 종료 후 AI 손님 지목 투표를 저장하는 ORM 모델입니다."""

    __tablename__ = "votes"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    voter_participant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=False,
    )
    target_participant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=False,
    )
    voted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)


class SessionResult(Base):
    """게임 종료 시점의 참가자별 결과 snapshot ORM 모델입니다."""

    __tablename__ = "session_results"
    __table_args__ = {"schema": GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    participant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=False,
    )
    final_score: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_winner: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revealed_participant_type: Mapped[str] = mapped_column(Text, nullable=False)
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class WordTurn(Base):
    """단어 게임의 라운드 안 개별 턴 정보를 저장하는 ORM 모델입니다."""

    __tablename__ = "turns"
    __table_args__ = {"schema": WORD_GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    phase_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_phases.id"),
        nullable=False,
    )
    participant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.session_participants.id"),
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    condition_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class WordSubmission(Base):
    """단어 게임 제출 단어와 정규화 결과를 저장하는 ORM 모델입니다."""

    __tablename__ = "submissions"
    __table_args__ = {"schema": WORD_GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    action_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.participant_actions.id"),
        nullable=False,
    )
    turn_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{WORD_GAME_SCHEMA}.turns.id"),
        nullable=False,
    )
    word: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_word: Mapped[str] = mapped_column(Text, nullable=False)
    dictionary_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class UsedWord(Base):
    """세션 안에서 이미 사용된 단어를 중복 방지용으로 저장하는 ORM 모델입니다."""

    __tablename__ = "used_words"
    __table_args__ = {"schema": WORD_GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{GAME_SCHEMA}.game_sessions.id"),
        nullable=False,
    )
    submission_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(f"{WORD_GAME_SCHEMA}.submissions.id"),
        nullable=False,
    )
    normalized_word: Mapped[str] = mapped_column(Text, nullable=False)


class ValidWord(Base):
    """단어 게임에서 제출 가능한 전체 유효 단어셋을 관리하는 ORM 모델입니다."""

    __tablename__ = "valid_words"
    __table_args__ = {"schema": WORD_GAME_SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid_v7,
    )
    game_type: Mapped[str] = mapped_column(Text, nullable=False)
    word: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_word: Mapped[str] = mapped_column(Text, nullable=False)
    starts_with: Mapped[str] = mapped_column(Text, nullable=False)
    ends_with: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
        onupdate=kst_now,
    )
