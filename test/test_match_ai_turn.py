from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

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


async def test_match_ai_turn_service_requests_agent_with_used_words_and_submits_answer() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    now = datetime(2026, 6, 13, tzinfo=KST)

    class FakeRepository:
        async def get_ai_turn_context(self, **kwargs):
            assert kwargs == {
                "game_session_public_id": game_session_public_id,
                "phase_id": phase_id,
            }
            return ai_context(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
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
    service = MatchAiTurnService(FakeRepository(), agent_client, progress_service)

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

    class FakeRepository:
        async def get_ai_turn_context(self, **kwargs):
            return ai_context(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
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
    service = MatchAiTurnService(FakeRepository(), agent_client, progress_service)

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
            "details": {"agent_reason": "no_available_word"},
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

    class FakeRepository:
        async def get_ai_turn_context(self, **kwargs):
            return ai_context(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
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
    service = MatchAiTurnService(FakeRepository(), agent_client, progress_service)

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

    class FakeRepository:
        async def get_ai_turn_context(self, **kwargs):
            return ai_context(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
            )

    progress_service = FakeProgressService()
    service = MatchAiTurnService(
        FakeRepository(),
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

    class FakeRepository:
        async def get_ai_turn_context(self, **kwargs):
            return ai_context(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
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
    service = MatchAiTurnService(FakeRepository(), agent_client, progress_service)

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

    class FakeRepository:
        async def get_ai_turn_context(self, **kwargs):
            return ai_context(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
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
    service = MatchAiTurnService(FakeRepository(), agent_client, progress_service)

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

    class FakeRepository:
        async def get_ai_turn_context(self, **kwargs):
            return ai_context(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
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
    service = MatchAiTurnService(FakeRepository(), agent_client, progress_service)

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


async def test_match_ai_turn_repository_builds_context_for_ai_actor() -> None:
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

    context = await repository.get_ai_turn_context(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
    )

    assert context == AiTurnContext(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        participant_id=participant_id,
        game_type="word_chain",
        used_words=["사과"],
        required_start_char="자",
    )
    used_word_lookup_sql = str(
        db_session.statements[2].compile(compile_kwargs={"literal_binds": True})
    )
    assert "used_words.round_number" in used_word_lookup_sql
