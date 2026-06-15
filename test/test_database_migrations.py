from pathlib import Path


MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"
INDEX_TUNING_MIGRATION = MIGRATION_DIR / "20260614_0007_tune_game_indexes.py"
VALID_WORDS_MIGRATION = MIGRATION_DIR / "20260614_0008_create_valid_words.py"
USED_WORD_ROUND_MIGRATION = MIGRATION_DIR / "20260615_0009_scope_used_words_by_round.py"
VALID_WORDS_PAYLOAD_MIGRATION = MIGRATION_DIR / "20260615_0010_add_valid_word_payload_fields.py"
WORD_CHAIN_GAME_TYPE_MIGRATION = MIGRATION_DIR / "20260615_0011_rename_word_chain_game_type.py"


def test_game_index_tuning_migration_declares_expected_revision_chain() -> None:
    """게임 인덱스 정리 migration이 현재 head 뒤에 연결되어 있는지 검증합니다."""
    migration = INDEX_TUNING_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260614_0007"' in migration
    assert 'down_revision: str | None = "20260613_0006"' in migration


def test_game_index_tuning_migration_adds_query_aligned_indexes() -> None:
    """현재 repository 조회 패턴에 맞춘 partial/composite index를 추가하는지 검증합니다."""
    migration = INDEX_TUNING_MIGRATION.read_text(encoding="utf-8")

    expected_fragments = [
        '"ix_rooms_open_created_at_desc"',
        '"closed_at IS NULL"',
        '"ix_room_members_active_room_joined_at"',
        '"left_at IS NULL"',
        '"ix_game_sessions_active_room_started_at"',
        "\"ended_at IS NULL AND status IN ('starting', 'playing', 'voting')\"",
        '"ix_score_ledger_session_participant"',
        '["session_id", "participant_id"]',
    ]
    for fragment in expected_fragments:
        assert fragment in migration


def test_game_index_tuning_migration_removes_redundant_single_column_indexes() -> None:
    """복합 unique index prefix로 커버되는 단일 index를 제거하는지 검증합니다."""
    migration = INDEX_TUNING_MIGRATION.read_text(encoding="utf-8")

    redundant_indexes = [
        "ix_session_participants_session_id",
        "ix_session_phases_session_id",
        "ix_participant_actions_session_id",
        "ix_game_events_session_id",
        "ix_votes_session_id",
        "ix_session_results_session_id",
        "ix_used_words_session_id",
        "ix_score_ledger_session_id",
    ]
    for index_name in redundant_indexes:
        assert f'"{index_name}"' in migration
        assert f'op.drop_index(\n        "{index_name}"' in migration


def test_game_index_tuning_migration_makes_resume_token_hash_unique() -> None:
    """재접속 토큰 hash index를 partial unique index로 교체하는지 검증합니다."""
    migration = INDEX_TUNING_MIGRATION.read_text(encoding="utf-8")

    assert 'op.drop_index(\n        "ix_session_participants_resume_token_hash"' in migration
    assert 'op.create_index(\n        "ix_session_participants_resume_token_hash"' in migration
    assert "unique=True" in migration
    assert 'postgresql_where=sa.text("resume_token_hash IS NOT NULL")' in migration


def test_valid_words_migration_declares_expected_revision_chain() -> None:
    """유효 단어셋 migration이 게임 index 정리 revision 뒤에 연결되어 있는지 검증합니다."""
    migration = VALID_WORDS_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260614_0008"' in migration
    assert 'down_revision: str | None = "20260614_0007"' in migration


def test_valid_words_migration_creates_dictionary_table_with_unique_lookup_index() -> None:
    """단어 유효성 판정용 table과 unique lookup index를 생성하는지 검증합니다."""
    migration = VALID_WORDS_MIGRATION.read_text(encoding="utf-8")

    expected_fragments = [
        'op.create_table(\n        "valid_words"',
        'sa.Column("game_type", sa.Text(), nullable=False)',
        'sa.Column("word", sa.Text(), nullable=False)',
        'sa.Column("normalized_word", sa.Text(), nullable=False)',
        'sa.Column("starts_with", sa.Text(), nullable=False)',
        'sa.Column("ends_with", sa.Text(), nullable=False)',
        'sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())',
        'sa.UniqueConstraint("game_type", "normalized_word", name="uq_valid_words_game_word")',
    ]
    for fragment in expected_fragments:
        assert fragment in migration

    assert "op.create_index(" not in migration


def test_used_words_round_scope_migration_declares_expected_revision_chain() -> None:
    """사용 단어 중복 범위 migration이 valid words revision 뒤에 연결되어 있는지 검증합니다."""
    migration = USED_WORD_ROUND_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260615_0009"' in migration
    assert 'down_revision: str | None = "20260614_0008"' in migration


def test_used_words_round_scope_migration_changes_unique_scope_to_round() -> None:
    """used_words 중복 제약이 세션 전체가 아니라 라운드 단위인지 검증합니다."""
    migration = USED_WORD_ROUND_MIGRATION.read_text(encoding="utf-8")

    expected_fragments = [
        'op.add_column(\n        "used_words"',
        'sa.Column("round_number", sa.Integer(), nullable=True)',
        "round_number = 1",
        "ck_used_words_round_number",
        "op.drop_constraint(",
        '"uq_used_words_session_word"',
        '["session_id", "round_number", "normalized_word"]',
        '"uq_used_words_session_round_word"',
    ]
    for fragment in expected_fragments:
        assert fragment in migration


def test_valid_words_payload_migration_declares_expected_revision_chain() -> None:
    """유효 단어셋 payload metadata migration이 used words revision 뒤에 연결되어 있는지 검증합니다."""
    migration = VALID_WORDS_PAYLOAD_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260615_0010"' in migration
    assert 'down_revision: str | None = "20260615_0009"' in migration


def test_valid_words_payload_migration_adds_jsonl_metadata_columns() -> None:
    """JSONL 단어 payload와 맞춘 초성, 음절, 길이, 사용 횟수 컬럼을 추가하는지 검증합니다."""
    migration = VALID_WORDS_PAYLOAD_MIGRATION.read_text(encoding="utf-8")

    expected_fragments = [
        'sa.Column("chosung", sa.Text(), nullable=True)',
        'sa.Column("syllables", postgresql.JSONB(astext_type=sa.Text()), nullable=True)',
        'sa.Column("length", sa.Integer(), nullable=True)',
        'sa.Column("used_count", sa.Integer(), nullable=False, server_default="0")',
        "UPDATE word_game.valid_words",
        "regexp_split_to_array(normalized_word, '')",
        "char_length(normalized_word)",
        "ck_valid_words_chosung_not_empty",
        "ck_valid_words_length_positive",
        "ck_valid_words_used_count_non_negative",
    ]
    for fragment in expected_fragments:
        assert fragment in migration


def test_word_chain_game_type_migration_declares_expected_revision_chain() -> None:
    """word_chain game type migration이 valid words payload revision 뒤에 연결되어 있는지 검증합니다."""
    migration = WORD_CHAIN_GAME_TYPE_MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260615_0011"' in migration
    assert 'down_revision: str | None = "20260615_0010"' in migration


def test_word_chain_game_type_migration_updates_stored_game_type_values() -> None:
    """기존 저장 데이터의 game_type 값을 word_chain 공개 계약으로 옮기는지 검증합니다."""
    migration = WORD_CHAIN_GAME_TYPE_MIGRATION.read_text(encoding="utf-8")

    expected_fragments = [
        "UPDATE game.rooms SET game_type = 'word_chain' WHERE game_type = 'shiritori'",
        "UPDATE game.game_sessions SET game_type = 'word_chain' WHERE game_type = 'shiritori'",
        "UPDATE word_game.valid_words SET game_type = 'word_chain' WHERE game_type = 'shiritori'",
        "UPDATE word_game.valid_words SET game_type = 'shiritori' WHERE game_type = 'word_chain'",
    ]
    for fragment in expected_fragments:
        assert fragment in migration
