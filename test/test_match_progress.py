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
from app.be.services.match_progress.turn_policy import MatchProgressTurnPolicy
from app.be.services.match_progress.word_submission_policy import WordSubmissionPolicy
from app.shared.core.korean import allowed_start_chars_with_dueum
from app.shared.core.exceptions import AppException


KST = ZoneInfo("Asia/Seoul")


@pytest.mark.parametrize(
    ("required_start_char", "allowed_start_chars"),
    [
        ("녀", {"녀", "여"}),
        ("냬", {"냬", "얘"}),
        ("라", {"라", "나"}),
        ("락", {"락", "낙"}),
        ("뢰", {"뢰", "뇌"}),
        ("륙", {"륙", "육"}),
        ("력", {"력", "역"}),
        ("럐", {"럐", "얘"}),
        ("나", {"나"}),
        ("가", {"가"}),
    ],
)
def test_allowed_start_chars_with_dueum_covers_initial_sound_law(
    required_start_char: str,
    allowed_start_chars: set[str],
) -> None:
    assert allowed_start_chars_with_dueum(required_start_char) == allowed_start_chars


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
        self.statements = []
        self.flushed_item_types = []
        self.observed_game_sessions = []
        self.flushed_game_session_current_phase_ids = []
        self.flush_count = 0
        self.committed = False

    async def execute(self, statement):
        self.statements.append(statement)
        result = self.results.pop(0)
        if (
            isinstance(result.scalar, GameSession)
            and result.scalar not in self.observed_game_sessions
        ):
            self.observed_game_sessions.append(result.scalar)
        return result

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1
        self.flushed_item_types.append([type(item).__name__ for item in self.added])
        self.flushed_game_session_current_phase_ids.append(
            [session.current_phase_id for session in self.observed_game_sessions]
        )
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
        game_type="word_chain",
        status="in_progress",
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
        started_at=datetime(2026, 6, 13, tzinfo=KST),
    )


def test_word_submission_policy_accepts_dueum_start_char_variants() -> None:
    policy = WordSubmissionPolicy()

    policy.ensure_word_starts_with_required_char(
        normalized_word="여자",
        required_start_char="녀",
    )
    policy.ensure_word_starts_with_required_char(
        normalized_word="나라",
        required_start_char="라",
    )
    policy.ensure_word_starts_with_required_char(
        normalized_word="육상",
        required_start_char="륙",
    )
    policy.ensure_word_starts_with_required_char(
        normalized_word="얘기",
        required_start_char="냬",
    )


class FakeAiFailureStepRepository:
    def __init__(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        reason: str,
        details: dict | None,
        created_at: datetime,
        event_sequence: int = 7,
        phase_finished: bool = False,
    ) -> None:
        self.session_id = uuid4()
        self.reason = reason
        self.details = details or {}
        self.created_at = created_at
        self.event_sequence = event_sequence
        self.committed = False
        self.game_session = build_session(self.session_id, game_session_public_id)
        self.game_session.current_phase_id = phase_id
        self.phase = SessionPhase(
            id=phase_id,
            session_id=self.session_id,
            phase_type="turn",
            phase_number=1,
            actor_participant_id=participant_id,
            condition_payload={"required_start_char": None},
            time_limit_seconds=10,
            started_at=created_at,
            deadline_at=datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
            finished_at=created_at if phase_finished else None,
        )
        self.turn = WordTurn(
            id=uuid4(),
            phase_id=phase_id,
            participant_id=participant_id,
            round_number=1,
            turn_number=1,
            condition_payload={"required_start_char": None},
        )
        self.participant = SessionParticipant(
            id=participant_id,
            session_id=self.session_id,
            user_id=None,
            participant_type="ai",
            display_name="2번 손님",
            seat_number=2,
            is_uninvited_guest=True,
        )
        self.action = ParticipantAction(
            id=uuid4(),
            session_id=self.session_id,
            phase_id=phase_id,
            participant_id=participant_id,
            action_type="ai_answer_failed",
            action_number=4,
            attempt_number=1,
            payload={
                "source": "agent",
                "reason": reason,
                "details": self.details,
            },
            submitted_at=created_at,
            response_ms=None,
            is_valid=False,
            reject_reason=reason,
        )

    async def get_game_session(self, public_id):
        return self.game_session

    async def get_phase(self, *, session_id, phase_id):
        return self.phase

    async def get_participant(self, *, session_id, participant_id):
        return self.participant

    async def get_turn_actor(self, *, session_id, phase_id):
        return self.turn, self.participant

    async def get_next_action_number(self, session_id):
        return self.action.action_number

    async def create_ai_answer_failed_action(self, **kwargs):
        assert kwargs["reason"] == self.reason
        assert kwargs["details"] == self.details
        return self.action

    async def flush(self):
        pass

    async def get_next_event_sequence(self, session_id):
        return self.event_sequence

    async def create_ai_answer_failed_event(self, **kwargs):
        return GameEvent(
            id=uuid4(),
            session_id=self.session_id,
            phase_id=self.phase.id,
            participant_id=self.participant.id,
            action_id=self.action.id,
            sequence=self.event_sequence,
            event_type="ai_answer_failed",
            payload=kwargs["payload"],
            created_at=self.created_at,
        )

    async def commit(self) -> None:
        self.committed = True


async def test_match_progress_service_commits_ai_failure_and_returns_broadcast_event() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    created_at = datetime(2026, 6, 13, tzinfo=KST)
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
        started_at=created_at,
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
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=True,
    )
    action = ParticipantAction(
        id=uuid4(),
        session_id=session_id,
        phase_id=phase_id,
        participant_id=participant_id,
        action_type="ai_answer_failed",
        action_number=4,
        attempt_number=1,
        payload={
            "source": "agent",
            "reason": "agent_timeout",
            "details": {"timeout_seconds": 3},
        },
        submitted_at=created_at,
        response_ms=None,
        is_valid=False,
        reject_reason="agent_timeout",
    )

    class FakeRepository:
        def __init__(self) -> None:
            self.calls = []

        async def get_game_session(self, public_id):
            self.calls.append("get_game_session")
            assert public_id == game_session_public_id
            return game_session

        async def get_phase(self, *, session_id, phase_id):
            self.calls.append("get_phase")
            assert session_id == game_session.id
            return phase

        async def get_participant(self, *, session_id, participant_id):
            self.calls.append("get_participant")
            assert session_id == game_session.id
            return participant

        async def get_turn_actor(self, *, session_id, phase_id):
            self.calls.append("get_turn_actor")
            assert session_id == game_session.id
            assert phase_id == phase.id
            return turn, participant

        async def get_next_action_number(self, session_id):
            self.calls.append("get_next_action_number")
            assert session_id == game_session.id
            return 4

        async def create_ai_answer_failed_action(self, **kwargs):
            self.calls.append("create_ai_answer_failed_action")
            assert kwargs["reason"] == "agent_timeout"
            assert kwargs["details"] == {"timeout_seconds": 3}
            return action

        async def flush(self):
            self.calls.append("flush")

        async def get_next_event_sequence(self, session_id):
            self.calls.append("get_next_event_sequence")
            assert session_id == game_session.id
            return 7

        async def create_ai_answer_failed_event(self, **kwargs):
            self.calls.append("create_ai_answer_failed_event")
            assert kwargs["action_id"] == action.id
            return GameEvent(
                id=uuid4(),
                session_id=session_id,
                phase_id=phase_id,
                participant_id=participant_id,
                action_id=action.id,
                sequence=7,
                event_type="ai_answer_failed",
                payload=kwargs["payload"],
                created_at=created_at,
            )

        async def commit(self) -> None:
            self.calls.append("commit")

    repository = FakeRepository()
    service = MatchProgressService(repository)

    event = await service.fail_ai_answer(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
        details={"timeout_seconds": 3},
    )

    assert repository.calls == [
        "get_game_session",
        "get_phase",
        "get_participant",
        "get_turn_actor",
        "get_next_action_number",
        "create_ai_answer_failed_action",
        "flush",
        "get_next_event_sequence",
        "create_ai_answer_failed_event",
        "flush",
        "commit",
    ]
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
            "reason": "answer_unavailable",
            "details": {"timeout_seconds": 3},
            "score_delta": 0,
            "created_at": datetime(2026, 6, 13, tzinfo=KST),
            "server_time": datetime(2026, 6, 13, tzinfo=KST),
        },
    }
    assert "participant_type" not in str(event.message)
    assert "agent" not in str(event.message)


async def test_match_progress_service_hides_internal_agent_failure_details() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    repository = FakeAiFailureStepRepository(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_error",
        details={
            "error": "agent answer request failed",
            "status_code": 503,
            "agent_reason": "no_available_word",
        },
        created_at=datetime(2026, 6, 13, tzinfo=KST),
    )
    service = MatchProgressService(repository)

    event = await service.fail_ai_answer(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_error",
        details={
            "error": "agent answer request failed",
            "status_code": 503,
            "agent_reason": "no_available_word",
        },
    )

    assert event is not None
    assert event.message["payload"]["reason"] == "answer_unavailable"
    assert event.message["payload"]["details"] == {}
    assert "agent" not in str(event.message)


async def test_match_progress_service_includes_rejected_ai_answer_word_in_failed_event() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    created_at = datetime(2026, 6, 13, tzinfo=KST)
    repository = FakeAiFailureStepRepository(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="word_not_in_dictionary",
        details={
            "agent_answer": "없는단어",
            "validation_reason": "word_not_in_dictionary",
        },
        created_at=created_at,
    )
    service = MatchProgressService(repository)

    event = await service.fail_ai_answer(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="word_not_in_dictionary",
        details={
            "agent_answer": "없는단어",
            "validation_reason": "word_not_in_dictionary",
        },
    )

    assert event is not None
    assert event.message["payload"]["result"] == "failed"
    assert event.message["payload"]["word"] == "없는단어"
    assert event.message["payload"]["normalized_word"] == "없는단어"
    assert event.message["payload"]["details"] == {"validation_reason": "word_not_in_dictionary"}
    assert "agent_answer" not in event.message["payload"]["details"]


async def test_match_progress_service_keeps_ai_failure_without_transition_payload() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    created_at = datetime(2026, 6, 13, tzinfo=KST)
    repository = FakeAiFailureStepRepository(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
        details={"timeout_seconds": 3},
        created_at=created_at,
        event_sequence=8,
    )
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
    repository = FakeAiFailureStepRepository(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
        details=None,
        created_at=datetime(2026, 6, 13, tzinfo=KST),
        phase_finished=True,
    )
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
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    next_participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
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
    action = ParticipantAction(
        id=uuid4(),
        session_id=session_id,
        phase_id=phase_id,
        participant_id=participant_id,
        action_type="turn_timeout",
        action_number=5,
        attempt_number=None,
        payload={
            "reason": "deadline_exceeded",
            "deadline_at": phase.deadline_at.isoformat(),
        },
        submitted_at=now,
        response_ms=None,
        is_valid=False,
        reject_reason="deadline_exceeded",
    )

    class FakeRepository:
        def __init__(self) -> None:
            self.calls = []

        async def get_game_session(self, public_id):
            self.calls.append("get_game_session")
            assert public_id == game_session_public_id
            return game_session

        async def get_phase(self, *, session_id, phase_id):
            self.calls.append("get_phase")
            return phase

        async def get_participant(self, *, session_id, participant_id):
            self.calls.append("get_participant")
            return participant

        async def get_turn_actor(self, *, session_id, phase_id):
            self.calls.append("get_turn_actor")
            return turn, participant

        async def list_participants(self, session_id):
            self.calls.append("list_participants")
            return [participant, next_participant]

        async def get_next_action_number(self, session_id):
            self.calls.append("get_next_action_number")
            return 5

        async def create_turn_timeout_action(self, **kwargs):
            self.calls.append("create_turn_timeout_action")
            return action

        async def flush(self):
            self.calls.append("flush")

        async def mark_phase_timeout(self, *, phase, now):
            self.calls.append("mark_phase_timeout")

        async def get_random_round_start_char(self, game_type):
            self.calls.append("get_random_round_start_char")
            return "가"

        async def create_session_phase(self, phase):
            self.calls.append("create_session_phase")

        async def mark_game_session_playing(self, *, game_session, current_phase_id):
            self.calls.append("mark_game_session_playing")

        async def create_word_turn(self, turn):
            self.calls.append("create_word_turn")

        async def get_next_event_sequence(self, session_id):
            self.calls.append("get_next_event_sequence")
            return 4

        async def create_turn_timeout_event(self, **kwargs):
            self.calls.append("create_turn_timeout_event")
            return GameEvent(
                id=uuid4(),
                session_id=session_id,
                phase_id=phase_id,
                participant_id=participant_id,
                action_id=action.id,
                sequence=4,
                event_type="turn_timeout",
                payload=kwargs["payload"],
                created_at=now,
            )

        async def commit(self) -> None:
            self.calls.append("commit")

    repository = FakeRepository()

    class FixedTurnPolicy(MatchProgressTurnPolicy):
        def choose_round_start_participant(self, participants):
            return next_participant

    service = MatchProgressService(repository, turn_policy=FixedTurnPolicy())

    event = await service.timeout_turn_if_due(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert repository.calls == [
        "get_game_session",
        "get_phase",
        "get_participant",
        "get_turn_actor",
        "list_participants",
        "get_next_action_number",
        "create_turn_timeout_action",
        "flush",
        "mark_phase_timeout",
        "get_random_round_start_char",
        "create_session_phase",
        "flush",
        "mark_game_session_playing",
        "create_word_turn",
        "get_next_event_sequence",
        "create_turn_timeout_event",
        "flush",
        "commit",
    ]
    assert event is not None
    payload = event.message["payload"]
    assert payload["event_sequence"] == 4
    assert payload["phase_id"] == phase_id
    assert payload["participant"] == {"display_name": "1번 손님", "seat_number": 1}
    assert payload["result"] == "timeout"
    assert payload["deadline_at"] == datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST)
    assert payload["next_turn"]["round_number"] == 2
    assert payload["next_turn"]["turn_number"] == 1
    assert payload["next_turn"]["actor_seat_number"] == 2
    assert payload["next_turn"]["required_start_char"] == "가"


async def test_match_progress_service_orchestrates_word_submission_repository_steps() -> None:
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
        condition_payload={"required_start_char": "륙"},
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
        condition_payload={"required_start_char": "륙"},
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
    action = ParticipantAction(
        id=uuid4(),
        session_id=session_id,
        phase_id=phase_id,
        participant_id=participant_id,
        action_type="word_submit",
        action_number=3,
        attempt_number=1,
        payload={"word": "육상", "normalized_word": "육상"},
        submitted_at=now,
        response_ms=None,
        is_valid=True,
    )
    submission = WordSubmission(
        id=uuid4(),
        action_id=action.id,
        turn_id=turn.id,
        word="육상",
        normalized_word="육상",
        dictionary_payload=None,
    )

    class FakeRepository:
        def __init__(self) -> None:
            self.calls = []

        async def get_game_session(self, public_id):
            self.calls.append("get_game_session")
            assert public_id == game_session_public_id
            return game_session

        async def get_phase(self, *, session_id, phase_id):
            self.calls.append("get_phase")
            assert session_id == game_session.id
            return phase

        async def get_turn_actor(self, *, session_id, phase_id):
            self.calls.append("get_turn_actor")
            return turn, participant

        async def get_valid_word(self, *, game_type, normalized_word):
            self.calls.append("get_valid_word")
            assert game_type == game_session.game_type
            assert normalized_word == "육상"
            return object()

        async def get_used_word(self, *, session_id, round_number, normalized_word):
            self.calls.append("get_used_word")
            return None

        async def list_participants(self, session_id):
            self.calls.append("list_participants")
            return [participant, next_participant]

        async def get_next_action_number(self, session_id):
            self.calls.append("get_next_action_number")
            return 3

        async def create_word_submit_action(self, **kwargs):
            self.calls.append("create_word_submit_action")
            assert kwargs["normalized_word"] == "육상"
            return action

        async def flush(self):
            self.calls.append("flush")

        async def create_word_submission(self, **kwargs):
            self.calls.append("create_word_submission")
            assert kwargs["action_id"] == action.id
            return submission

        async def create_used_word(self, **kwargs):
            self.calls.append("create_used_word")
            assert kwargs["submission_id"] == submission.id

        async def create_word_submission_score(self, **kwargs):
            self.calls.append("create_word_submission_score")
            assert kwargs["score_delta"] == 10

        async def create_session_phase(self, phase):
            self.calls.append("create_session_phase")

        async def mark_phase_success(self, *, phase, now):
            self.calls.append("mark_phase_success")

        async def mark_game_session_playing(self, *, game_session, current_phase_id):
            self.calls.append("mark_game_session_playing")

        async def create_word_turn(self, turn):
            self.calls.append("create_word_turn")

        async def get_next_event_sequence(self, session_id):
            self.calls.append("get_next_event_sequence")
            return 6

        async def create_word_accepted_event(self, **kwargs):
            self.calls.append("create_word_accepted_event")
            return GameEvent(
                id=uuid4(),
                session_id=session_id,
                phase_id=phase_id,
                participant_id=participant_id,
                action_id=action.id,
                sequence=6,
                event_type="word.accepted",
                payload=kwargs["payload"],
                created_at=now,
            )

        async def commit(self):
            self.calls.append("commit")

    repository = FakeRepository()
    service = MatchProgressService(repository)

    event = await service.submit_word(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        word=" 육상 ",
        now=now,
    )

    assert repository.calls == [
        "get_game_session",
        "get_phase",
        "get_turn_actor",
        "get_valid_word",
        "get_used_word",
        "list_participants",
        "get_next_action_number",
        "create_word_submit_action",
        "flush",
        "create_word_submission",
        "flush",
        "create_used_word",
        "create_word_submission_score",
        "create_session_phase",
        "flush",
        "mark_phase_success",
        "mark_game_session_playing",
        "create_word_turn",
        "get_next_event_sequence",
        "create_word_accepted_event",
        "flush",
        "commit",
    ]
    assert event.message["payload"]["result"] == "accepted"
    assert event.message["payload"]["next_turn"]["required_start_char"] == "상"


async def test_match_progress_service_commits_word_rejection_and_returns_broadcast_event() -> None:
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
    action = ParticipantAction(
        id=uuid4(),
        session_id=session_id,
        phase_id=phase_id,
        participant_id=participant_id,
        action_type="word_reject",
        action_number=7,
        attempt_number=1,
        payload={
            "word": "사과",
            "normalized_word": "사과",
            "reason": "word_start_char_mismatch",
            "details": {"required_start_char": "가"},
        },
        submitted_at=now,
        response_ms=None,
        is_valid=False,
        reject_reason="word_start_char_mismatch",
    )

    class FakeRepository:
        def __init__(self) -> None:
            self.calls = []

        async def get_game_session(self, public_id):
            self.calls.append("get_game_session")
            assert public_id == game_session_public_id
            return game_session

        async def get_phase(self, *, session_id, phase_id):
            self.calls.append("get_phase")
            assert session_id == game_session.id
            return phase

        async def get_turn_actor(self, *, session_id, phase_id):
            self.calls.append("get_turn_actor")
            assert session_id == game_session.id
            assert phase_id == phase.id
            return turn, participant

        async def get_next_action_number(self, session_id):
            self.calls.append("get_next_action_number")
            assert session_id == game_session.id
            return 7

        async def create_word_reject_action(self, **kwargs):
            self.calls.append("create_word_reject_action")
            assert kwargs["normalized_word"] == "사과"
            assert kwargs["reason"] == "word_start_char_mismatch"
            assert kwargs["details"] == {"required_start_char": "가"}
            return action

        async def flush(self):
            self.calls.append("flush")

        async def create_word_rejection_score(self, **kwargs):
            self.calls.append("create_word_rejection_score")
            assert kwargs["action_id"] == action.id
            assert kwargs["score_delta"] == -5

        async def get_next_event_sequence(self, session_id):
            self.calls.append("get_next_event_sequence")
            assert session_id == game_session.id
            return 12

        async def create_word_rejected_event(self, **kwargs):
            self.calls.append("create_word_rejected_event")
            assert kwargs["action_id"] == action.id
            assert kwargs["payload"]["score_delta"] == -5
            return GameEvent(
                id=uuid4(),
                session_id=session_id,
                phase_id=phase_id,
                participant_id=participant_id,
                action_id=action.id,
                sequence=12,
                event_type="word.rejected",
                payload=kwargs["payload"],
                created_at=now,
            )

        async def commit(self) -> None:
            self.calls.append("commit")

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

    assert repository.calls == [
        "get_game_session",
        "get_phase",
        "get_turn_actor",
        "get_next_action_number",
        "create_word_reject_action",
        "flush",
        "create_word_rejection_score",
        "get_next_event_sequence",
        "create_word_rejected_event",
        "flush",
        "commit",
    ]
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
            "server_time": now,
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
    service = MatchProgressService(repository)

    event_message = await service.fail_ai_answer(
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
    assert event_message is not None
    assert event_message.message["payload"]["event_sequence"] == 9
    assert event_message.message["payload"]["participant"]["display_name"] == "2번 손님"
    assert "next_status" not in event_message.message["payload"]
    assert "next_turn" not in event_message.message["payload"]
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
    service = MatchProgressService(repository)

    event_message = await service.fail_ai_answer(
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
    assert event_message is not None
    assert "next_turn" not in event_message.message["payload"]
    assert "next_status" not in event_message.message["payload"]


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
    service = MatchProgressService(repository)

    event_message = await service.fail_ai_answer(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        reason="agent_timeout",
    )

    assert event_message is None
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
    service = MatchProgressService(repository)

    event_message = await service.timeout_turn_if_due(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

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
    assert event.payload["round_number"] == 1
    assert event.payload["deadline_at"] == deadline_at.isoformat()
    assert event.payload["next_status"] == "voting"
    assert event.payload["voting_deadline_at"] == voting_phase.deadline_at.isoformat()
    assert voting_phase.phase_type == "voting"
    assert phase.result_status == "timeout"
    assert phase.finished_at == now
    assert event_message is not None
    assert event_message.message["payload"]["event_sequence"] == 10
    assert event_message.message["payload"]["deadline_at"] == deadline_at
    assert event_message.message["payload"]["next_status"] == "voting"
    assert db_session.flush_count == 3
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
            FakeResult(scalar="나"),
            FakeResult(scalar=12),
        ]
    )
    repository = MatchProgressRepository(db_session)

    class FixedTurnPolicy(MatchProgressTurnPolicy):
        def choose_round_start_participant(self, participants):
            return next_participant

    service = MatchProgressService(repository, turn_policy=FixedTurnPolicy())

    event_message = await service.timeout_turn_if_due(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    action, next_phase, next_turn, event = db_session.added
    assert isinstance(next_phase, SessionPhase)
    assert next_phase.phase_number == 5
    assert next_phase.actor_participant_id == next_participant_id
    assert next_phase.condition_payload == {"required_start_char": "나"}
    assert next_phase.started_at == datetime(2026, 6, 13, 0, 0, 16, tzinfo=KST)
    assert next_phase.deadline_at == datetime(2026, 6, 13, 0, 0, 26, tzinfo=KST)
    assert isinstance(next_turn, WordTurn)
    assert next_turn.round_number == 2
    assert next_turn.turn_number == 1
    assert next_turn.condition_payload == {"required_start_char": "나"}
    assert next_turn.participant_id == next_participant_id
    assert game_session.current_phase_id == next_phase.id
    assert game_session.status == "playing"
    assert event.payload["next_turn"]["round_number"] == 2
    assert event.payload["next_turn"]["actor_seat_number"] == 2
    assert event.payload["next_turn"]["required_start_char"] == "나"
    assert event.payload["next_turn"]["started_at"] == "2026-06-13T00:00:16+09:00"
    assert event_message is not None
    assert event_message.message["payload"]["next_turn"]["round_number"] == 2
    assert event_message.message["payload"]["next_turn"]["required_start_char"] == "나"
    assert event_message.message["payload"]["next_turn"]["started_at"] == datetime(
        2026, 6, 13, 0, 0, 16, tzinfo=KST
    )
    assert action.action_type == "turn_timeout"
    assert db_session.flushed_item_types[0] == ["ParticipantAction"]
    assert db_session.flushed_item_types[1] == ["ParticipantAction", "SessionPhase"]
    assert db_session.flushed_item_types[2] == [
        "ParticipantAction",
        "SessionPhase",
        "WordTurn",
        "GameEvent",
    ]
    assert db_session.flushed_game_session_current_phase_ids[0] == [phase_id]


async def test_match_progress_timeout_uses_random_round_start_actor() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    next_participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
    game_session = build_session(session_id, game_session_public_id)
    game_session.rule_config = {"max_rounds": 2, "turn_time_seconds": 10}
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
    next_participant = SessionParticipant(
        id=next_participant_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=True,
    )

    class FixedTurnPolicy(MatchProgressTurnPolicy):
        def choose_round_start_participant(self, participants):
            return participant

    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(scalar=participant),
            FakeResult(row=(turn, participant)),
            FakeResult(scalars=[participant, next_participant]),
            FakeResult(scalar=8),
            FakeResult(scalar="나"),
            FakeResult(scalar=12),
        ]
    )
    repository = MatchProgressRepository(db_session)
    service = MatchProgressService(repository, turn_policy=FixedTurnPolicy())

    event_message = await service.timeout_turn_if_due(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    _action, next_phase, next_turn, _event = db_session.added
    assert next_phase.actor_participant_id == participant_id
    assert next_turn.participant_id == participant_id
    assert event_message is not None
    assert event_message.message["payload"]["next_turn"]["actor_seat_number"] == 1
    assert db_session.flushed_game_session_current_phase_ids[1] == [phase_id]
    assert db_session.flushed_game_session_current_phase_ids[2] == [next_phase.id]


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
    service = MatchProgressService(repository)

    event_message = await service.timeout_turn_if_due(
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
    assert event_message is not None
    assert "next_turn" not in event_message.message["payload"]
    assert event_message.message["payload"]["next_status"] == "voting"
    assert db_session.flushed_item_types[0] == ["ParticipantAction"]
    assert db_session.flushed_item_types[1] == ["ParticipantAction", "SessionPhase"]
    assert db_session.flushed_item_types[2] == [
        "ParticipantAction",
        "SessionPhase",
        "GameEvent",
    ]
    assert db_session.flushed_game_session_current_phase_ids[0] == [phase_id]
    assert db_session.flushed_game_session_current_phase_ids[1] == [phase_id]
    assert db_session.flushed_game_session_current_phase_ids[2] == [voting_phase.id]


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
    service = MatchProgressService(repository)

    event_message = await service.submit_word(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        word=" 사과 ",
        now=now,
    )

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
    assert used_word.round_number == 1
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
    assert event_message.message["payload"]["next_turn"]["actor_seat_number"] == 2
    assert event_message.message["payload"]["next_turn"]["required_start_char"] == "과"
    assert db_session.flushed_item_types[0] == ["ParticipantAction"]
    assert db_session.flushed_item_types[1] == ["ParticipantAction", "WordSubmission"]
    assert db_session.flushed_item_types[2] == [
        "ParticipantAction",
        "WordSubmission",
        "UsedWord",
        "ScoreLedger",
        "SessionPhase",
    ]
    assert db_session.flushed_item_types[3] == [
        "ParticipantAction",
        "WordSubmission",
        "UsedWord",
        "ScoreLedger",
        "SessionPhase",
        "WordTurn",
        "GameEvent",
    ]
    assert db_session.committed is True
    used_word_lookup_sql = str(
        db_session.statements[4].compile(compile_kwargs={"literal_binds": True})
    )
    assert "used_words.round_number" in used_word_lookup_sql


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
    service = MatchProgressService(repository)

    with pytest.raises(AppException) as exc_info:
        await service.submit_word(
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


async def test_match_progress_repository_returns_none_when_session_is_missing() -> None:
    db_session = FakeDbSession([FakeResult(scalar=None)])
    repository = MatchProgressRepository(db_session)

    game_session = await repository.get_game_session(uuid4())

    assert game_session is None


async def test_match_progress_service_rejects_missing_session() -> None:
    db_session = FakeDbSession([FakeResult(scalar=None)])
    repository = MatchProgressRepository(db_session)
    service = MatchProgressService(repository)

    with pytest.raises(AppException) as exc_info:
        await service.submit_word(
            game_session_public_id=uuid4(),
            phase_id=uuid4(),
            participant_id=uuid4(),
            word="사과",
            now=datetime(2026, 6, 13, tzinfo=KST),
        )

    assert exc_info.value.details == {"reason": "game_session_not_found"}
    assert db_session.added == []


async def test_match_progress_service_rejects_missing_turn_actor() -> None:
    session_id = uuid4()
    game_session = build_session(session_id, uuid4())
    phase = SessionPhase(
        id=uuid4(),
        session_id=session_id,
        phase_type="turn",
        phase_number=1,
        actor_participant_id=uuid4(),
        condition_payload={"required_start_char": None},
        time_limit_seconds=10,
        started_at=datetime(2026, 6, 13, tzinfo=KST),
        deadline_at=datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=phase),
            FakeResult(row=None),
        ]
    )
    repository = MatchProgressRepository(db_session)
    service = MatchProgressService(repository)

    with pytest.raises(AppException) as exc_info:
        await service.submit_word(
            game_session_public_id=game_session.public_id,
            phase_id=phase.id,
            participant_id=phase.actor_participant_id,
            word="사과",
            now=datetime(2026, 6, 13, tzinfo=KST),
        )

    assert exc_info.value.details == {"reason": "turn_not_found"}
    assert db_session.added == []


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
    service = MatchProgressService(repository)

    event_message = await service.reject_word(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        word=" 사과 ",
        reason="word_start_char_mismatch",
        details={"required_start_char": "가"},
        now=now,
    )

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
    assert event_message.message["payload"]["score_delta"] == -5
    assert db_session.flushed_item_types[0] == ["ParticipantAction"]
    assert db_session.flushed_item_types[1] == ["ParticipantAction", "ScoreLedger", "GameEvent"]
    assert db_session.committed is True
