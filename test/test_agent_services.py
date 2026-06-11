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


class FakeVllmService:
    def __init__(self, generated_word: str | None = None) -> None:
        self.generated_word = generated_word
        self.calls: list[dict] = []

    async def generate_fallback(
        self,
        game_type,
        condition: str,
        used_words: set[str],
    ) -> str | None:
        self.calls.append(
            {
                "game_type": game_type,
                "condition": condition,
                "used_words": used_words,
            }
        )
        return self.generated_word


def build_service(
    repository: FakeWordRepository,
    vllm_service: VllmService | FakeVllmService | None = None,
) -> AgentService:
    return AgentService(
        CandidateService(
            repository,
            shortlist_size=10,
            random_source=random.Random(0),
        ),
        build_handler_registry(),
        InMemoryIdempotencyStore(),
        QdrantUsageService(repository),
        vllm_service
        or VllmService(
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


async def test_no_qdrant_candidate_uses_vllm_fallback_once() -> None:
    vllm_service = FakeVllmService("줄사랑")
    service = build_service(FakeWordRepository(), vllm_service)

    execution = await service.answer(answer_request())

    assert execution.response.status == "ok"
    assert execution.response.answer == "줄사랑"
    assert execution.usage_word is None
    assert vllm_service.calls == [
        {
            "game_type": "shiritori",
            "condition": "줄",
            "used_words": {"거미줄"},
        }
    ]


async def test_candidate_response_records_only_returned_answer() -> None:
    repository = FakeWordRepository([candidate("줄넘기")])
    vllm_service = FakeVllmService("줄사랑")
    service = build_service(repository, vllm_service)

    execution = await service.answer(answer_request())
    await service.record_usage(execution.usage_word)

    assert execution.response.answer == "줄넘기"
    assert repository.incremented == ["줄넘기"]
    assert vllm_service.calls == []


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


async def test_candidate_selection_uses_random_shortlist_of_ten() -> None:
    candidates = [candidate(f"줄{index:02d}") for index in range(20)]
    repository = FakeWordRepository(candidates)
    service = CandidateService(
        repository,
        shortlist_size=10,
        random_source=random.Random(0),
    )

    result = await service.select(
        AgentAnswerRequest(
            room_id="room-1",
            game_type="shiritori",
            used_words=[],
            last_char="줄",
        ),
        ShiritoriHandler(),
    )

    assert result.selected is not None
    assert len(result.shortlist) == 10
    assert len({item.word for item in result.shortlist}) == 10
    assert result.selected in result.shortlist
    assert repository.find_calls == 1


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
