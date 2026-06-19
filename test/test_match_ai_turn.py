from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.be.models.game import GameSession, SessionParticipant, SessionPhase, UsedWord, WordTurn
from app.be.repository.match_ai import MatchAiTurnRepository
from app.be.services.match_ai import AiTurnContext, MatchAiTurnService
from app.be.services.match_progress import MatchBroadcastEvent
from app.shared.clients.agent import AgentAnswerResult, AgentClientError
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


KST = ZoneInfo("Asia/Seoul")


class FakeScalarCollection:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeResult:
    def __init__(self, *, scalar=None, row=None, scalars=None) -> None:
        self.scalar = scalar
        self.row = row
        self.scalar_rows = scalars or []

    def scalar_one_or_none(self):
        return self.scalar

    def one_or_none(self):
        return self.row

    def scalars(self):
        return FakeScalarCollection(self.scalar_rows)


class FakeDbSession:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)


class FakeAgentAnswerClient:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.requests = []

    async def get_answer(self, payload):
        self.requests.append(payload)
        if self.error:
            raise self.error
        return self.result


class FakeProgressService:
    def __init__(self) -> None:
        self.submitted_words = []
        self.failures = []
        self.rejected_words = []

    async def submit_word(self, **kwargs):
        self.submitted_words.append(kwargs)
        return MatchBroadcastEvent(
            game_session_public_id=kwargs["game_session_public_id"],
            message={
                "type": "match.turn.resolved",
                "payload": {"result": "accepted", "word": kwargs["word"]},
            },
        )

    async def fail_ai_answer(self, **kwargs):
        self.failures.append(kwargs)
        return MatchBroadcastEvent(
            game_session_public_id=kwargs["game_session_public_id"],
            message={
                "type": "match.turn.resolved",
                "payload": {"result": "failed", "reason": kwargs["reason"]},
            },
        )

    async def reject_word(self, **kwargs):
        self.rejected_words.append(kwargs)
        return MatchBroadcastEvent(
            game_session_public_id=kwargs["game_session_public_id"],
            message={
                "type": "match.turn.resolved",
                "payload": {
                    "result": "rejected",
                    "word": kwargs["word"],
                    "reason": kwargs["reason"],
                },
            },
        )


def ai_context(
    *,
    game_session_public_id: UUID,
    phase_id: UUID,
    participant_id: UUID,
) -> AiTurnContext:
    return AiTurnContext(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        game_type="word_chain",
        used_words=["사과", "과자"],
        required_start_char="자",
    )


class FakeAiTurnRepository:
    def __init__(self, context: AiTurnContext | None) -> None:
        self.context = context
        self.session_id = uuid4()
        self.game_session = None
        self.phase = None
        self.turn = None
        self.participant = None
        self.calls = []
        if context is not None:
            self.game_session = GameSession(
                id=self.session_id,
                public_id=context.game_session_public_id,
                room_id=uuid4(),
                game_type=context.game_type,
                status="playing",
                rule_config={"max_rounds": 8, "turn_time_seconds": 10},
            )
            self.phase = SessionPhase(
                id=context.phase_id,
                session_id=self.session_id,
                phase_type="turn",
                phase_number=1,
                actor_participant_id=context.participant_id,
                condition_payload={"required_start_char": context.required_start_char},
            )
            self.turn = WordTurn(
                id=uuid4(),
                phase_id=context.phase_id,
                participant_id=context.participant_id,
                round_number=1,
                turn_number=1,
                condition_payload={"required_start_char": context.required_start_char},
            )
            self.participant = SessionParticipant(
                id=context.participant_id,
                session_id=self.session_id,
                user_id=None,
                participant_type="ai",
                display_name="2번 손님",
                seat_number=2,
                is_uninvited_guest=True,
            )

    async def get_game_session(self, game_session_public_id):
        self.calls.append(("get_game_session", game_session_public_id))
        if self.context is None:
            return None
        assert game_session_public_id == self.context.game_session_public_id
        return self.game_session

    async def get_active_turn_actor(self, *, session_id, phase_id):
        self.calls.append(("get_active_turn_actor", session_id, phase_id))
        assert self.context is not None
        assert session_id == self.session_id
        assert phase_id == self.context.phase_id
        return self.phase, self.turn, self.participant

    async def list_used_words(self, *, session_id, round_number):
        self.calls.append(("list_used_words", session_id, round_number))
        assert self.context is not None
        assert session_id == self.session_id
        assert round_number == self.turn.round_number
        return self.context.used_words


async def test_match_ai_turn_service_requests_agent_with_used_words_and_submits_answer() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, tzinfo=KST)

    repository = FakeAiTurnRepository(
        ai_context(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
        )
    )

    agent_client = FakeAgentAnswerClient(
        result=AgentAnswerResult(
            request_id=str(phase_id),
            room_id=str(game_session_public_id),
            game_type="word_chain",
            answer="자동차",
            status="ok",
            reason=None,
        )
    )
    progress_service = FakeProgressService()
    service = MatchAiTurnService(repository, agent_client, progress_service)

    event = await service.play_ai_turn(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    request = agent_client.requests[0]
    assert request.request_id == str(phase_id)
    assert request.room_id == str(game_session_public_id)
    assert request.game_type == "word_chain"
    assert request.used_words == ["사과", "과자"]
    assert request.last_char == "자"
    assert request.condition.last_char == "자"
    assert repository.calls == [
        ("get_game_session", game_session_public_id),
        ("get_active_turn_actor", repository.session_id, phase_id),
        ("list_used_words", repository.session_id, 1),
    ]
    assert progress_service.submitted_words == [
        {
            "game_session_public_id": game_session_public_id,
            "phase_id": phase_id,
            "participant_id": participant_id,
            "word": "자동차",
            "now": now,
        }
    ]
    assert event is not None
    assert event.message["type"] == "match.turn.resolved"
    assert event.message["payload"]["result"] == "accepted"


async def test_match_ai_turn_service_records_failure_when_agent_has_no_candidate() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, tzinfo=KST)

    repository = FakeAiTurnRepository(
        ai_context(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
        )
    )

    agent_client = FakeAgentAnswerClient(
        result=AgentAnswerResult(
            request_id=str(phase_id),
            room_id=str(game_session_public_id),
            game_type="word_chain",
            answer=None,
            status="no_candidate",
            reason="no_available_word",
        )
    )
    progress_service = FakeProgressService()
    service = MatchAiTurnService(repository, agent_client, progress_service)

    event = await service.play_ai_turn(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert progress_service.submitted_words == []
    assert progress_service.failures == [
        {
            "game_session_public_id": game_session_public_id,
            "phase_id": phase_id,
            "participant_id": participant_id,
            "reason": "no_candidate",
            "details": {"agent_reason": "no_available_word", "agent_answer": ""},
        }
    ]
    assert event is not None
    assert event.message["type"] == "match.turn.resolved"
    assert event.message["payload"]["result"] == "failed"


async def test_match_ai_turn_service_preserves_no_candidate_answer_word() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, tzinfo=KST)

    repository = FakeAiTurnRepository(
        ai_context(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
        )
    )

    agent_client = FakeAgentAnswerClient(
        result=AgentAnswerResult(
            request_id=str(phase_id),
            room_id=str(game_session_public_id),
            game_type="word_chain",
            answer="과자",
            status="no_candidate",
            reason="word_not_in_dictionary",
        )
    )
    progress_service = FakeProgressService()
    service = MatchAiTurnService(repository, agent_client, progress_service)

    event = await service.play_ai_turn(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert progress_service.submitted_words == []
    assert progress_service.failures == []
    assert progress_service.rejected_words == [
        {
            "game_session_public_id": game_session_public_id,
            "phase_id": phase_id,
            "participant_id": participant_id,
            "word": "과자",
            "reason": "word_not_in_dictionary",
            "details": {"validation_reason": "word_not_in_dictionary"},
            "now": now,
        }
    ]
    assert event is not None
    assert event.message["type"] == "match.turn.resolved"
    assert event.message["payload"]["result"] == "rejected"
    assert event.message["payload"]["word"] == "과자"


async def test_match_ai_turn_service_records_failure_when_agent_request_fails() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, tzinfo=KST)

    repository = FakeAiTurnRepository(
        ai_context(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
        )
    )

    progress_service = FakeProgressService()
    service = MatchAiTurnService(
        repository,
        FakeAgentAnswerClient(error=AgentClientError("agent answer request timed out")),
        progress_service,
    )

    event = await service.play_ai_turn(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert progress_service.failures[0]["reason"] == "agent_timeout"
    assert progress_service.failures[0]["details"] == {
        "error": "agent answer request timed out",
        "status_code": None,
    }
    assert event is not None
    assert event.message["type"] == "match.turn.resolved"
    assert event.message["payload"]["result"] == "failed"


async def test_match_ai_turn_service_rejects_agent_answer_like_player_word() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, tzinfo=KST)

    repository = FakeAiTurnRepository(
        ai_context(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
        )
    )

    class RejectingProgressService(FakeProgressService):
        async def submit_word(self, **kwargs):
            self.submitted_words.append(kwargs)
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "word_not_in_dictionary"},
            )

    agent_client = FakeAgentAnswerClient(
        result=AgentAnswerResult(
            request_id=str(phase_id),
            room_id=str(game_session_public_id),
            game_type="word_chain",
            answer="없는단어",
            status="ok",
            reason=None,
        )
    )
    progress_service = RejectingProgressService()
    service = MatchAiTurnService(repository, agent_client, progress_service)

    event = await service.play_ai_turn(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert progress_service.failures == []
    assert progress_service.rejected_words == [
        {
            "game_session_public_id": game_session_public_id,
            "phase_id": phase_id,
            "participant_id": participant_id,
            "word": "없는단어",
            "reason": "word_not_in_dictionary",
            "details": {"validation_reason": "word_not_in_dictionary"},
            "now": now,
        }
    ]
    assert event is not None
    assert event.message["type"] == "match.turn.resolved"
    assert event.message["payload"]["result"] == "rejected"
    assert event.message["payload"]["word"] == "없는단어"


async def test_match_ai_turn_service_ignores_answer_when_phase_already_finished() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, tzinfo=KST)

    repository = FakeAiTurnRepository(
        ai_context(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
        )
    )

    class StaleProgressService(FakeProgressService):
        async def submit_word(self, **kwargs):
            self.submitted_words.append(kwargs)
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "phase_already_finished"},
            )

    agent_client = FakeAgentAnswerClient(
        result=AgentAnswerResult(
            request_id=str(phase_id),
            room_id=str(game_session_public_id),
            game_type="word_chain",
            answer="자동차",
            status="ok",
            reason=None,
        )
    )
    progress_service = StaleProgressService()
    service = MatchAiTurnService(repository, agent_client, progress_service)

    event = await service.play_ai_turn(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert event is None
    assert progress_service.failures == []


async def test_match_ai_turn_service_converts_late_answer_to_turn_timeout() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)

    repository = FakeAiTurnRepository(
        ai_context(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
        )
    )

    class LateProgressService(FakeProgressService):
        def __init__(self) -> None:
            super().__init__()
            self.timeout_calls = []

        async def submit_word(self, **kwargs):
            self.submitted_words.append(kwargs)
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "turn_deadline_exceeded"},
            )

        async def timeout_turn_if_due(self, **kwargs):
            self.timeout_calls.append(kwargs)
            return MatchBroadcastEvent(
                game_session_public_id=kwargs["game_session_public_id"],
                message={
                    "type": "match.turn.resolved",
                    "payload": {"phase_id": kwargs["phase_id"], "result": "timeout"},
                },
            )

    agent_client = FakeAgentAnswerClient(
        result=AgentAnswerResult(
            request_id=str(phase_id),
            room_id=str(game_session_public_id),
            game_type="word_chain",
            answer="자동차",
            status="ok",
            reason=None,
        )
    )
    progress_service = LateProgressService()
    service = MatchAiTurnService(repository, agent_client, progress_service)

    event = await service.play_ai_turn(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert event is not None
    assert event.message["type"] == "match.turn.resolved"
    assert event.message["payload"]["result"] == "timeout"
    assert progress_service.timeout_calls == [
        {
            "game_session_public_id": game_session_public_id,
            "phase_id": phase_id,
            "now": now,
        }
    ]
    assert progress_service.failures == []


async def test_match_ai_turn_service_rejects_missing_session() -> None:
    service = MatchAiTurnService(
        FakeAiTurnRepository(None),
        FakeAgentAnswerClient(result=None),
        FakeProgressService(),
    )

    with pytest.raises(AppException) as exc_info:
        await service.play_ai_turn(
            game_session_public_id=uuid4(),
            phase_id=uuid4(),
            now=datetime(2026, 6, 13, tzinfo=KST),
        )

    assert exc_info.value.details == {"reason": "game_session_not_found"}


async def test_match_ai_turn_service_rejects_missing_active_turn() -> None:
    context = ai_context(
        game_session_public_id=uuid4(),
        phase_id=uuid4(),
        participant_id=uuid4(),
    )

    class MissingActiveTurnRepository(FakeAiTurnRepository):
        async def get_active_turn_actor(self, *, session_id, phase_id):
            return None

    service = MatchAiTurnService(
        MissingActiveTurnRepository(context),
        FakeAgentAnswerClient(result=None),
        FakeProgressService(),
    )

    with pytest.raises(AppException) as exc_info:
        await service.play_ai_turn(
            game_session_public_id=context.game_session_public_id,
            phase_id=context.phase_id,
            now=datetime(2026, 6, 13, tzinfo=KST),
        )

    assert exc_info.value.details == {"reason": "active_turn_not_found"}


async def test_match_ai_turn_service_ignores_non_ai_actor() -> None:
    context = ai_context(
        game_session_public_id=uuid4(),
        phase_id=uuid4(),
        participant_id=uuid4(),
    )
    repository = FakeAiTurnRepository(context)
    repository.participant.participant_type = "user"
    agent_client = FakeAgentAnswerClient(result=None)
    service = MatchAiTurnService(repository, agent_client, FakeProgressService())

    event = await service.play_ai_turn(
        game_session_public_id=context.game_session_public_id,
        phase_id=context.phase_id,
        now=datetime(2026, 6, 13, tzinfo=KST),
    )

    assert event is None
    assert agent_client.requests == []


async def test_match_ai_turn_repository_returns_rows_for_ai_turn_queries() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    session_id = uuid4()
    participant_id = uuid4()
    game_session = GameSession(
        id=session_id,
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="playing",
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
    )
    phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="turn",
        phase_number=2,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": "자"},
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=2,
        condition_payload={"required_start_char": "자"},
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
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(row=(phase, turn, participant)),
            FakeResult(
                scalars=[
                    UsedWord(
                        id=uuid4(),
                        session_id=session_id,
                        round_number=1,
                        submission_id=uuid4(),
                        normalized_word="사과",
                    )
                ]
            ),
        ]
    )
    repository = MatchAiTurnRepository(db_session)

    fetched_session = await repository.get_game_session(game_session_public_id)
    turn_actor = await repository.get_active_turn_actor(
        session_id=session_id,
        phase_id=phase_id,
    )
    used_words = await repository.list_used_words(session_id=session_id, round_number=1)

    assert fetched_session is game_session
    assert turn_actor == (phase, turn, participant)
    assert used_words == ["사과"]
    used_word_lookup_sql = str(
        db_session.statements[2].compile(compile_kwargs={"literal_binds": True})
    )
    assert "used_words.round_number" in used_word_lookup_sql


async def test_match_ai_turn_repository_returns_none_when_session_is_missing() -> None:
    db_session = FakeDbSession([FakeResult(scalar=None)])
    repository = MatchAiTurnRepository(db_session)

    game_session = await repository.get_game_session(uuid4())

    assert game_session is None


async def test_match_ai_turn_repository_returns_none_when_active_turn_is_missing() -> None:
    db_session = FakeDbSession([FakeResult(row=None)])
    repository = MatchAiTurnRepository(db_session)

    turn_actor = await repository.get_active_turn_actor(
        session_id=uuid4(),
        phase_id=uuid4(),
    )

    assert turn_actor is None
