from app.be.models.game import (
    GAME_SCHEMA,
    WORD_GAME_SCHEMA,
    GameEvent,
    ParticipantAction,
    ScoreLedger,
    SessionPhase,
    SessionResult,
    StateSnapshot,
    Vote,
    WordSubmission,
    WordTurn,
    UsedWord,
)


def test_game_progress_models_use_game_schema_tables() -> None:
    assert SessionPhase.__table__.schema == GAME_SCHEMA
    assert SessionPhase.__tablename__ == "session_phases"
    assert ParticipantAction.__table__.schema == GAME_SCHEMA
    assert ParticipantAction.__tablename__ == "participant_actions"
    assert StateSnapshot.__table__.schema == GAME_SCHEMA
    assert StateSnapshot.__tablename__ == "state_snapshots"
    assert GameEvent.__table__.schema == GAME_SCHEMA
    assert GameEvent.__tablename__ == "game_events"
    assert ScoreLedger.__table__.schema == GAME_SCHEMA
    assert ScoreLedger.__tablename__ == "score_ledger"
    assert Vote.__table__.schema == GAME_SCHEMA
    assert Vote.__tablename__ == "votes"
    assert SessionResult.__table__.schema == GAME_SCHEMA
    assert SessionResult.__tablename__ == "session_results"


def test_word_game_models_use_word_game_schema_tables() -> None:
    assert WordTurn.__table__.schema == WORD_GAME_SCHEMA
    assert WordTurn.__tablename__ == "turns"
    assert WordSubmission.__table__.schema == WORD_GAME_SCHEMA
    assert WordSubmission.__tablename__ == "submissions"
    assert UsedWord.__table__.schema == WORD_GAME_SCHEMA
    assert UsedWord.__tablename__ == "used_words"
