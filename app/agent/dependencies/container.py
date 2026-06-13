from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient

from app.agent.core.config import AgentSettings
from app.agent.repository.qdrant import QdrantWordRepository
from app.agent.services.answer import AgentService
from app.agent.services.candidate import CandidateService
from app.agent.services.game_handlers import build_handler_registry
from app.agent.services.idempotency import InMemoryIdempotencyStore
from app.agent.services.stack import StackService
from app.agent.services.usage import QdrantUsageService
from app.agent.services.vllm import VllmService
from app.agent.services.word import WordService


@dataclass
class AgentServiceContainer:
    """Agent 런타임 서비스와 외부 클라이언트 수명주기를 묶습니다."""

    qdrant_client: AsyncQdrantClient
    repository: QdrantWordRepository
    agent_service: AgentService
    stack_service: StackService

    @classmethod
    def build(cls, settings: AgentSettings) -> "AgentServiceContainer":
        """설정값으로 Agent의 repository와 service graph를 생성합니다."""
        qdrant_client = AsyncQdrantClient(
            url=settings.qdrant_url,
            check_compatibility=False,
        )
        repository = QdrantWordRepository(
            qdrant_client,
            settings.qdrant_collection,
        )
        idempotency_store = InMemoryIdempotencyStore(
            ttl_seconds=settings.idempotency_ttl_seconds,
            max_entries=settings.idempotency_max_entries,
        )
        usage_service = QdrantUsageService(repository)
        vllm_service = VllmService(
            settings.vllm_base_url,
            settings.vllm_model_name,
            enabled=settings.use_vllm,
            timeout_seconds=settings.vllm_timeout_seconds,
        )
        agent_service = AgentService(
            CandidateService(
                repository,
                candidate_limit=settings.candidate_limit,
                shortlist_size=settings.candidate_shortlist_size,
            ),
            build_handler_registry(),
            idempotency_store,
            usage_service,
            vllm_service,
        )
        stack_service = StackService(
            repository,
            WordService(),
            idempotency_store,
        )
        return cls(
            qdrant_client=qdrant_client,
            repository=repository,
            agent_service=agent_service,
            stack_service=stack_service,
        )

    async def close(self) -> None:
        """Agent가 소유한 Qdrant client 연결을 종료합니다."""
        await self.qdrant_client.close()
