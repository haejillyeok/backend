from dataclasses import dataclass

from app.agent.repository.qdrant import WordRepository
from app.agent.schemas.request.data_stack import DataStackRequest
from app.agent.schemas.response.data_stack import DataStackResponse
from app.agent.services.idempotency import IdempotencyStore
from app.agent.services.word import WordService
from app.agent.utils.hashing import stable_hash


@dataclass(frozen=True)
class StackJob:
    job_id: str
    payloads: tuple[dict, ...]
    overwrite_existing: bool
    preserve_ai_used_count: bool


@dataclass(frozen=True)
class StackExecution:
    response: DataStackResponse
    job: StackJob | None


class StackService:
    """비동기 단어 적재 job 생성과 Qdrant upsert를 조정합니다."""

    def __init__(
        self,
        repository: WordRepository,
        word_service: WordService,
        idempotency_store: IdempotencyStore,
    ) -> None:
        self._repository = repository
        self._word_service = word_service
        self._idempotency_store = idempotency_store

    async def accept(self, request: DataStackRequest) -> StackExecution:
        """적재 요청을 정규화하고 중복 요청에는 새 background job을 만들지 않습니다."""
        game_types = [game_type.value for game_type in request.game_types]
        payloads = self._word_service.prepare_payloads(
            request.words,
            game_types,
            is_valid=request.options.is_valid,
            is_banned=request.options.is_banned,
        )
        key_hash = self._request_hash(request, payloads)
        key = f"stack:{request.request_id or key_hash}"

        async def create_job() -> StackJob:
            return StackJob(
                job_id=f"job-{key_hash[:8]}",
                payloads=tuple(payloads),
                overwrite_existing=request.options.overwrite_existing,
                preserve_ai_used_count=request.options.preserve_ai_used_count,
            )

        job, created = await self._idempotency_store.get_or_create(key, create_job)
        response = DataStackResponse(
            request_id=request.request_id,
            job_id=job.job_id,
            received_count=len(job.payloads),
        )
        return StackExecution(response=response, job=job if created else None)

    async def process(self, job: StackJob) -> None:
        """수락된 job의 단어 payload를 Qdrant에 적재합니다."""
        await self._repository.upsert_words(
            job.payloads,
            overwrite_existing=job.overwrite_existing,
            preserve_ai_used_count=job.preserve_ai_used_count,
        )

    @staticmethod
    def _request_hash(request: DataStackRequest, payloads: list[dict]) -> str:
        return stable_hash(
            {
                "source": request.source,
                "payloads": payloads,
                "options": request.options.model_dump(),
            }
        )
