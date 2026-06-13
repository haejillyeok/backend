from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.be.models.game import (
    GameEvent,
    GameSession,
    ParticipantAction,
    ScoreLedger,
    SessionParticipant,
)
from app.be.models.game import SessionPhase, UsedWord, WordSubmission, WordTurn
from app.be.repository.match_progress import MatchProgressRepository
from app.be.services.match_progress import MatchProgressService
from app.shared.core.exceptions import AppException


KST = ZoneInfo("Asia/Seoul")


class FakeResult:
    def __init__(self, *, scalar=None, row=None, scalars=None) -> None:
        self.scalar = scalar
        self.row = row
        self.scalar_rows = scalars or []

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar

    def one_or_none(self):
        return self.row

    def scalars(self):
        return FakeScalarCollection(self.scalar_rows)


class FakeScalarCollection:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeDbSession:
    def __init__(self, results=None) -> None:
        self.results = list(results or [])
        self.added = []
        self.flush_count = 0
        self.committed = False

    async def execute(self, statement):
        return self.results.pop(0)

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    async def commit(self) -> None:
        self.committed = True


def build_session(session_id: UUID, public_id: UUID) -> GameSession:
    return GameSession(
        id=session_id,
        public_id=public_id,
        room_id=uuid4(),
        game_type="shiritori",
        status="in_progress",
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
        started_at=datetime(2026, 6, 13, tzinfo=KST),
    )


async def test_match_progress_service_commits_ai_failure_and_returns_broadcast_event() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    record_result = None

    class FakeRepository:
        def __init__(self) -> None:
            self.committed = False

        async def record_ai_answer_failure(self, **kwargs):
            nonlocal record_result
            from app.be.services.match_progress import AiAnswerFailureRecord

            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["phase_id"] == phase_id
            assert kwargs["participant_id"] == participant_id
            assert kwargs["reason"] == "agent_timeout"
            record_result = AiAnswerFailureRecord(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
                display_name="2번 손님",
                seat_number=2,
                action_id=uuid4(),
                event_id=uuid4(),
                event_sequence=7,
                reason="agent_timeout",
                details={"timeout_seconds": 3},
                created_at=datetime(2026, 6, 13, tzinfo=KST),
            )
            return record_result

        async def commit(self) -> None:
            self.committed = True

    repository = FakeRepository()
    service = MatchProgressService(repository)

    event = await service.fail_ai_answer(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
        details={"timeout_seconds": 3},
    )

    assert repository.committed is True
    assert event.game_session_public_id == game_session_public_id
    assert event.message == {
        "type": "match.turn.resolved",
        "payload": {
            "event_sequence": 7,
            "phase_id": phase_id,
            "participant": {
                "display_name": "2번 손님",
                "seat_number": 2,
            },
            "result": "failed",
            "word": None,
            "normalized_word": None,
            "reason": "agent_timeout",
            "details": {"timeout_seconds": 3},
            "score_delta": 0,
            "created_at": datetime(2026, 6, 13, tzinfo=KST),
        },
    }
    assert "participant_type" not in str(event.message)


async def test_match_progress_service_keeps_ai_failure_without_transition_payload() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    created_at = datetime(2026, 6, 13, tzinfo=KST)

    class FakeRepository:
        def __init__(self) -> None:
            self.committed = False

        async def record_ai_answer_failure(self, **kwargs):
            from app.be.services.match_progress import AiAnswerFailureRecord

            return AiAnswerFailureRecord(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
                display_name="2번 손님",
                seat_number=2,
                action_id=uuid4(),
                event_id=uuid4(),
                event_sequence=8,
                reason="agent_timeout",
                details={"timeout_seconds": 3},
                created_at=created_at,
            )

        async def commit(self) -> None:
            self.committed = True

    repository = FakeRepository()
    service = MatchProgressService(repository)

    event = await service.fail_ai_answer(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
        details={"timeout_seconds": 3},
    )

    assert repository.committed is True
    assert event.message["payload"]["result"] == "failed"
    assert "next_turn" not in event.message["payload"]
    assert "next_status" not in event.message["payload"]
    assert "voting_deadline_at" not in event.message["payload"]


async def test_match_progress_service_ignores_stale_ai_failure_after_turn_finished() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()

    class FakeRepository:
        def __init__(self) -> None:
            self.committed = False

        async def record_ai_answer_failure(self, **kwargs):
            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["phase_id"] == phase_id
            assert kwargs["participant_id"] == participant_id
            return None

        async def commit(self) -> None:
            self.committed = True

    repository = FakeRepository()
    service = MatchProgressService(repository)

    event = await service.fail_ai_answer(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
    )

    assert event is None
    assert repository.committed is False


async def test_match_progress_service_commits_turn_timeout_and_returns_broadcast_event() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)

    class FakeRepository:
        def __init__(self) -> None:
            self.committed = False

        async def record_turn_timeout(self, **kwargs):
            from app.be.services.match_progress import TurnTimeoutRecord

            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["phase_id"] == phase_id
            assert kwargs["now"] == now
            return TurnTimeoutRecord(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=uuid4(),
                display_name="1번 손님",
                seat_number=1,
                action_id=uuid4(),
                event_id=uuid4(),
                event_sequence=4,
                deadline_at=datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
                created_at=now,
            )

        async def commit(self) -> None:
            self.committed = True

    repository = FakeRepository()
    service = MatchProgressService(repository)

    event = await service.timeout_turn_if_due(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert repository.committed is True
    assert event is not None
    assert event.message == {
        "type": "match.turn.resolved",
        "payload": {
            "event_sequence": 4,
            "phase_id": phase_id,
            "participant": {
                "display_name": "1번 손님",
                "seat_number": 1,
            },
            "result": "timeout",
            "word": None,
            "normalized_word": None,
            "reason": "deadline_exceeded",
            "details": {},
            "score_delta": 0,
            "deadline_at": datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
            "created_at": now,
        },
    }


async def test_match_progress_service_commits_word_submission_and_returns_broadcast_event() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 5, tzinfo=KST)

    class FakeRepository:
        def __init__(self) -> None:
            self.committed = False

        async def record_word_submission(self, **kwargs):
            from app.be.services.match_progress import MatchTurnEventPayload, WordSubmissionRecord

            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["phase_id"] == phase_id
            assert kwargs["participant_id"] == participant_id
            assert kwargs["word"] == "사과"
            assert kwargs["now"] == now
            return WordSubmissionRecord(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
                display_name="1번 손님",
                seat_number=1,
                word="사과",
                normalized_word="사과",
                action_id=uuid4(),
                submission_id=uuid4(),
                event_id=uuid4(),
                event_sequence=11,
                score_delta=10,
                next_turn=MatchTurnEventPayload(
                    phase_id=uuid4(),
                    round_number=1,
                    turn_number=2,
                    actor_seat_number=2,
                    deadline_at=datetime(2026, 6, 13, 0, 0, 15, tzinfo=KST),
                    required_start_char="과",
                ),
                created_at=now,
            )

        async def commit(self) -> None:
            self.committed = True

    repository = FakeRepository()
    service = MatchProgressService(repository)

    event = await service.submit_word(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        word="사과",
        now=now,
    )

    assert repository.committed is True
    assert event.message["type"] == "match.turn.resolved"
    assert event.message["payload"]["participant"] == {
        "display_name": "1번 손님",
        "seat_number": 1,
    }
    assert event.message["payload"]["result"] == "accepted"
    assert event.message["payload"]["word"] == "사과"
    assert event.message["payload"]["normalized_word"] == "사과"
    assert event.message["payload"]["reason"] is None
    assert event.message["payload"]["details"] == {}
    assert event.message["payload"]["score_delta"] == 10
    assert event.message["payload"]["next_turn"]["actor_seat_number"] == 2
    assert event.message["payload"]["next_turn"]["required_start_char"] == "과"


async def test_match_progress_service_commits_word_rejection_and_returns_broadcast_event() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 5, tzinfo=KST)

    class FakeRepository:
        def __init__(self) -> None:
            self.committed = False

        async def record_word_rejection(self, **kwargs):
            from app.be.services.match_progress import WordRejectionRecord

            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["phase_id"] == phase_id
            assert kwargs["participant_id"] == participant_id
            assert kwargs["word"] == "사과"
            assert kwargs["reason"] == "word_start_char_mismatch"
            assert kwargs["details"] == {"required_start_char": "가"}
            assert kwargs["now"] == now
            return WordRejectionRecord(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
                display_name="1번 손님",
                seat_number=1,
                word="사과",
                normalized_word="사과",
                action_id=uuid4(),
                event_id=uuid4(),
                event_sequence=12,
                reason="word_start_char_mismatch",
                details={"required_start_char": "가"},
                score_delta=-5,
                created_at=now,
            )

        async def commit(self) -> None:
            self.committed = True

    repository = FakeRepository()
    service = MatchProgressService(repository)

    event = await service.reject_word(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        word="사과",
        reason="word_start_char_mismatch",
        details={"required_start_char": "가"},
        now=now,
    )

    assert repository.committed is True
    assert event.message == {
        "type": "match.turn.resolved",
        "payload": {
            "event_sequence": 12,
            "phase_id": phase_id,
            "participant": {
                "display_name": "1번 손님",
                "seat_number": 1,
            },
            "result": "rejected",
            "word": "사과",
            "normalized_word": "사과",
            "reason": "word_start_char_mismatch",
            "details": {"required_start_char": "가"},
            "score_delta": -5,
            "created_at": now,
        },
    }


async def test_match_progress_repository_records_ai_answer_failure() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    game_session = build_session(session_id, game_session_public_id)
    game_session.rule_config = {"max_rounds": 1, "turn_time_seconds": 10}
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=3,
        actor_participant_id=participant_id,
        condition_payload={"last_char": "가"},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=3,
        condition_payload={"last_char": "가"},
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=False,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(scalar=participant),
            FakeResult(row=(turn, participant)),
            FakeResult(scalar=4),
            FakeResult(scalar=8),
        ]
    )
    repository = MatchProgressRepository(db_session)

    record = await repository.record_ai_answer_failure(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
        details={"timeout_seconds": 3},
        response_ms=3000,
    )
    await repository.commit()

    action = db_session.added[0]
    event = db_session.added[1]
    assert isinstance(action, ParticipantAction)
    assert action.action_type == "ai_answer_failed"
    assert action.action_number == 5
    assert action.is_valid is False
    assert action.reject_reason == "agent_timeout"
    assert action.response_ms == 3000
    assert action.payload == {
        "source": "agent",
        "reason": "agent_timeout",
        "details": {"timeout_seconds": 3},
    }
    assert isinstance(event, GameEvent)
    assert event.sequence == 9
    assert event.event_type == "ai_answer_failed"
    assert event.payload["participant"] == {"display_name": "2번 손님", "seat_number": 2}
    assert event.payload["result_status"] == "failed"
    assert "next_status" not in event.payload
    assert "voting_deadline_at" not in event.payload
    assert phase.result_status is None
    assert phase.finished_at is None
    assert record.event_sequence == 9
    assert record.display_name == "2번 손님"
    assert record.next_status is None
    assert record.next_turn is None
    assert db_session.flush_count == 2
    assert db_session.committed is True


async def test_match_progress_repository_keeps_turn_open_after_ai_failure_at_max_rounds() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    game_session = build_session(session_id, game_session_public_id)
    game_session.rule_config = {"max_rounds": 1, "turn_time_seconds": 10}
    game_session.current_phase_id = phase_id
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=4,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": "과"},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=4,
        condition_payload={"required_start_char": "과"},
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=False,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(scalar=participant),
            FakeResult(row=(turn, participant)),
            FakeResult(scalar=4),
            FakeResult(scalar=8),
        ]
    )
    repository = MatchProgressRepository(db_session)

    record = await repository.record_ai_answer_failure(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
        details={"timeout_seconds": 3},
        response_ms=3000,
    )

    action, event = db_session.added
    assert action.action_type == "ai_answer_failed"
    assert event.payload["result_status"] == "failed"
    assert "next_status" not in event.payload
    assert "voting_deadline_at" not in event.payload
    assert game_session.status == "in_progress"
    assert game_session.current_phase_id == phase_id
    assert phase.finished_at is None
    assert phase.result_status is None
    assert record.next_turn is None
    assert record.next_status is None


async def test_match_progress_repository_ignores_stale_ai_failure_after_phase_finished() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    finished_at = datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST)
    game_session = build_session(session_id, game_session_public_id)
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=3,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": "가"},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
        deadline_at=finished_at,
        finished_at=finished_at,
        result_status="timeout",
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=True,
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=2,
        condition_payload={"required_start_char": "가"},
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(scalar=participant),
            FakeResult(row=(turn, participant)),
            FakeResult(scalars=[participant]),
            FakeResult(scalar=4),
            FakeResult(scalar=8),
        ]
    )
    repository = MatchProgressRepository(db_session)

    record = await repository.record_ai_answer_failure(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
    )

    assert record is None
    assert db_session.added == []
    assert phase.result_status == "timeout"


async def test_match_progress_repository_records_turn_timeout_when_deadline_passed() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
    deadline_at = datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST)
    game_session = build_session(session_id, game_session_public_id)
    game_session.rule_config = {"max_rounds": 1, "turn_time_seconds": 10}
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=3,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": "가"},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
        deadline_at=deadline_at,
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=3,
        condition_payload={"required_start_char": "가"},
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(scalar=participant),
            FakeResult(row=(turn, participant)),
            FakeResult(scalars=[participant]),
            FakeResult(scalar=6),
            FakeResult(scalar=9),
        ]
    )
    repository = MatchProgressRepository(db_session)

    record = await repository.record_turn_timeout(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )
    await repository.commit()

    action = db_session.added[0]
    voting_phase = db_session.added[1]
    event = db_session.added[2]
    assert isinstance(action, ParticipantAction)
    assert action.action_type == "turn_timeout"
    assert action.action_number == 7
    assert action.is_valid is False
    assert action.reject_reason == "deadline_exceeded"
    assert action.submitted_at == now
    assert action.payload == {
        "reason": "deadline_exceeded",
        "deadline_at": deadline_at.isoformat(),
    }
    assert isinstance(event, GameEvent)
    assert event.sequence == 10
    assert event.event_type == "turn_timeout"
    assert event.payload["participant"] == {"display_name": "1번 손님", "seat_number": 1}
    assert event.payload["deadline_at"] == deadline_at.isoformat()
    assert event.payload["next_status"] == "voting"
    assert event.payload["voting_deadline_at"] == voting_phase.deadline_at.isoformat()
    assert voting_phase.phase_type == "voting"
    assert phase.result_status == "timeout"
    assert phase.finished_at == now
    assert record.event_sequence == 10
    assert record.deadline_at == deadline_at
    assert record.next_status == "voting"
    assert db_session.flush_count == 2
    assert db_session.committed is True


async def test_match_progress_repository_starts_next_round_after_timeout_before_max_rounds() -> (
    None
):
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    next_participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
    deadline_at = datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST)
    game_session = build_session(session_id, game_session_public_id)
    game_session.rule_config = {"max_rounds": 2, "turn_time_seconds": 10}
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=4,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": "과"},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
        deadline_at=deadline_at,
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=4,
        condition_payload={"required_start_char": "과"},
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    next_participant = SessionParticipant(
        id=next_participant_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=True,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(scalar=participant),
            FakeResult(row=(turn, participant)),
            FakeResult(scalars=[participant, next_participant]),
            FakeResult(scalar=8),
            FakeResult(scalar=12),
        ]
    )
    repository = MatchProgressRepository(db_session)

    record = await repository.record_turn_timeout(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    action, next_phase, next_turn, event = db_session.added
    assert isinstance(next_phase, SessionPhase)
    assert next_phase.phase_number == 5
    assert next_phase.actor_participant_id == next_participant_id
    assert next_phase.condition_payload == {"required_start_char": None}
    assert next_phase.deadline_at == datetime(2026, 6, 13, 0, 0, 21, tzinfo=KST)
    assert isinstance(next_turn, WordTurn)
    assert next_turn.round_number == 2
    assert next_turn.turn_number == 1
    assert next_turn.participant_id == next_participant_id
    assert game_session.current_phase_id == next_phase.id
    assert game_session.status == "playing"
    assert event.payload["next_turn"]["round_number"] == 2
    assert event.payload["next_turn"]["actor_seat_number"] == 2
    assert record.next_turn is not None
    assert record.next_turn.round_number == 2
    assert action.action_type == "turn_timeout"


async def test_match_progress_repository_moves_to_voting_after_timeout_at_max_rounds() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
    game_session = build_session(session_id, game_session_public_id)
    game_session.rule_config = {"max_rounds": 1, "turn_time_seconds": 10}
    game_session.current_phase_id = phase_id
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=4,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": "과"},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
        deadline_at=datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=4,
        condition_payload={"required_start_char": "과"},
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(scalar=participant),
            FakeResult(row=(turn, participant)),
            FakeResult(scalars=[participant]),
            FakeResult(scalar=8),
            FakeResult(scalar=12),
        ]
    )
    repository = MatchProgressRepository(db_session)

    record = await repository.record_turn_timeout(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    action, voting_phase, event = db_session.added
    assert action.action_type == "turn_timeout"
    assert isinstance(voting_phase, SessionPhase)
    assert voting_phase.phase_type == "voting"
    assert voting_phase.deadline_at == datetime(2026, 6, 13, 0, 0, 31, tzinfo=KST)
    assert event.payload["next_status"] == "voting"
    assert event.payload["voting_deadline_at"] == voting_phase.deadline_at.isoformat()
    assert "next_turn" not in event.payload
    assert game_session.status == "voting"
    assert game_session.current_phase_id == voting_phase.id
    assert record.next_turn is None
    assert record.next_status == "voting"


async def test_match_progress_repository_accepts_word_submission_and_starts_next_turn() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    next_participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 5, tzinfo=KST)
    game_session = build_session(session_id, game_session_public_id)
    game_session.current_phase_id = phase_id
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=1,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": None},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
        deadline_at=datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=1,
        condition_payload={"required_start_char": None},
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    next_participant = SessionParticipant(
        id=next_participant_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=True,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(row=(turn, participant)),
            FakeResult(scalar=object()),
            FakeResult(scalar=None),
            FakeResult(scalars=[participant, next_participant]),
            FakeResult(scalar=2),
            FakeResult(scalar=5),
        ]
    )
    repository = MatchProgressRepository(db_session)

    record = await repository.record_word_submission(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        word=" 사과 ",
        now=now,
    )
    await repository.commit()

    action, submission, used_word, score, next_phase, next_turn, event = db_session.added
    assert isinstance(action, ParticipantAction)
    assert action.action_type == "word_submit"
    assert action.action_number == 3
    assert action.is_valid is True
    assert action.payload == {"word": "사과", "normalized_word": "사과"}
    assert isinstance(submission, WordSubmission)
    assert submission.word == "사과"
    assert submission.normalized_word == "사과"
    assert isinstance(used_word, UsedWord)
    assert used_word.session_id == session_id
    assert used_word.normalized_word == "사과"
    assert isinstance(score, ScoreLedger)
    assert score.score_delta == 10
    assert score.reason == "word_accepted"
    assert isinstance(next_phase, SessionPhase)
    assert next_phase.phase_number == 2
    assert next_phase.actor_participant_id == next_participant_id
    assert next_phase.condition_payload == {"required_start_char": "과"}
    assert next_phase.deadline_at == datetime(2026, 6, 13, 0, 0, 15, tzinfo=KST)
    assert isinstance(next_turn, WordTurn)
    assert next_turn.round_number == 1
    assert next_turn.turn_number == 2
    assert next_turn.participant_id == next_participant_id
    assert next_turn.condition_payload == {"required_start_char": "과"}
    assert isinstance(event, GameEvent)
    assert event.event_type == "word.accepted"
    assert event.sequence == 6
    assert event.payload["word"] == "사과"
    assert event.payload["next_turn"]["actor_seat_number"] == 2
    assert phase.result_status == "success"
    assert phase.finished_at == now
    assert game_session.current_phase_id == next_phase.id
    assert game_session.status == "playing"
    assert record.next_turn.actor_seat_number == 2
    assert record.next_turn.required_start_char == "과"
    assert db_session.flush_count == 1
    assert db_session.committed is True


async def test_match_progress_repository_rejects_word_missing_from_dictionary() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    next_participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 5, tzinfo=KST)
    game_session = build_session(session_id, game_session_public_id)
    game_session.current_phase_id = phase_id
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=1,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": None},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
        deadline_at=datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=1,
        condition_payload={"required_start_char": None},
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    next_participant = SessionParticipant(
        id=next_participant_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=True,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(row=(turn, participant)),
            FakeResult(scalar=None),
            FakeResult(scalars=[participant, next_participant]),
            FakeResult(scalar=2),
            FakeResult(scalar=5),
        ]
    )
    repository = MatchProgressRepository(db_session)

    with pytest.raises(AppException) as exc_info:
        await repository.record_word_submission(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
            word="없는단어",
            now=now,
        )

    assert exc_info.value.details == {"reason": "word_not_in_dictionary"}
    assert db_session.added == []
    assert phase.finished_at is None
    assert game_session.current_phase_id == phase_id


async def test_match_progress_repository_records_word_rejection_without_advancing_turn() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 5, tzinfo=KST)
    game_session = build_session(session_id, game_session_public_id)
    game_session.current_phase_id = phase_id
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=1,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": "가"},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
        deadline_at=datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=1,
        condition_payload={"required_start_char": "가"},
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(row=(turn, participant)),
            FakeResult(scalar=6),
            FakeResult(scalar=9),
        ]
    )
    repository = MatchProgressRepository(db_session)

    record = await repository.record_word_rejection(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        word=" 사과 ",
        reason="word_start_char_mismatch",
        details={"required_start_char": "가"},
        now=now,
    )
    await repository.commit()

    action, score, event = db_session.added
    assert isinstance(action, ParticipantAction)
    assert action.action_type == "word_reject"
    assert action.action_number == 7
    assert action.is_valid is False
    assert action.reject_reason == "word_start_char_mismatch"
    assert action.payload == {
        "word": "사과",
        "normalized_word": "사과",
        "reason": "word_start_char_mismatch",
        "details": {"required_start_char": "가"},
    }
    assert isinstance(score, ScoreLedger)
    assert score.score_delta == -5
    assert score.reason == "word_start_char_mismatch"
    assert isinstance(event, GameEvent)
    assert event.sequence == 10
    assert event.event_type == "word.rejected"
    assert event.payload["reason"] == "word_start_char_mismatch"
    assert phase.finished_at is None
    assert game_session.current_phase_id == phase_id
    assert record.score_delta == -5
    assert db_session.committed is True
