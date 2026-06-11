import random

from app.agent.schemas.request.answer import AgentAnswerRequest
from app.agent.schemas.request.data_stack import DataStackRequest
from app.agent.services.answer import AgentService
from app.agent.services.candidate import CandidateService
from app.agent.services.game_handlers import build_handler_registry
from app.agent.services.game_handlers.shiritori import ShiritoriHandler
from app.agent.services.idempotency import InMemoryIdempotencyStore
from app.agent.services.stack import StackService
from app.agent.services.usage import QdrantUsageService
from app.agent.services.vllm import VllmService
from app.agent.services.word import WordService
from test.agent_fakes import FakeWordRepository, candidate


def build_service(repository: FakeWordRepository) -> AgentService:
    return AgentService(
        CandidateService(repository, random_source=random.Random(0)),
        build_handler_registry(),
        InMemoryIdempotencyStore(),
        QdrantUsageService(repository),
        VllmService(
            "http://vllm:8000",
            "shiritori-llm",
            enabled=False,
            timeout_seconds=1,
        ),
    )


def answer_request(request_id: str = "req-1") -> AgentAnswerRequest:
    return AgentAnswerRequest(
        request_id=request_id,
        room_id="room-1",
        game_type="shiritori",
        used_words=["거미줄"],
        last_char="줄",
    )


async def test_no_candidate_returns_without_usage() -> None:
    execution = await build_service(FakeWordRepository()).answer(answer_request())

    assert execution.response.status == "no_candidate"
    assert execution.response.answer is None
    assert execution.response.reason == "no_available_word"
    assert execution.usage_word is None


async def test_candidate_response_records_only_returned_answer() -> None:
    repository = FakeWordRepository([candidate("줄넘기")])
    service = build_service(repository)

    execution = await service.answer(answer_request())
    await service.record_usage(execution.usage_word)

    assert execution.response.answer == "줄넘기"
    assert repository.incremented == ["줄넘기"]


async def test_duplicate_answer_request_queries_and_counts_once() -> None:
    repository = FakeWordRepository([candidate("줄넘기")])
    service = build_service(repository)

    first = await service.answer(answer_request())
    second = await service.answer(answer_request())

    assert first.response == second.response
    assert first.usage_word == "줄넘기"
    assert second.usage_word is None
    assert repository.find_calls == 1


async def test_used_words_are_excluded_after_single_repository_query() -> None:
    repository = FakeWordRepository(
        [
            candidate("줄넘기"),
            candidate("줄다리기", used_count=1),
        ]
    )
    service = CandidateService(repository, random_source=random.Random(0))
    request = AgentAnswerRequest(
        room_id="room-1",
        game_type="shiritori",
        used_words=["줄넘기"],
        last_char="줄",
    )

    result = await service.select(request, ShiritoriHandler())

    assert result is not None
    assert result.selected.word == "줄다리기"
    assert repository.find_calls == 1


async def test_lower_usage_and_shorter_words_are_preferred() -> None:
    repository = FakeWordRepository(
        [
            candidate("줄넘기", used_count=10),
            candidate("줄자", used_count=0),
        ]
    )
    service = CandidateService(repository, random_source=random.Random(0))

    result = await service.select(
        AgentAnswerRequest(
            room_id="room-1",
            game_type="shiritori",
            used_words=[],
            last_char="줄",
        ),
        ShiritoriHandler(),
    )

    assert result is not None
    assert result.selected.word == "줄자"


async def test_stack_builds_payload_and_avoids_duplicate_job() -> None:
    repository = FakeWordRepository()
    service = StackService(
        repository,
        WordService(),
        InMemoryIdempotencyStore(),
    )
    request = DataStackRequest(
        request_id="stack-1",
        game_types=["shiritori", "chosung", "contains"],
        words=["사과", " 사과 ", "고구마밭"],
    )

    first = await service.accept(request)
    second = await service.accept(request)

    assert first.response.received_count == 2
    assert first.job is not None
    assert first.job.payloads[0]["chosung"] == "ㅅㄱ"
    assert second.job is None
    await service.process(first.job)
    assert len(repository.upsert_calls) == 1
