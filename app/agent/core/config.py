from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Agent의 Qdrant, vLLM, 인증 설정을 환경변수에서 읽습니다."""

    app_env: str = "dev"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "game_words"
    vllm_base_url: str = "http://vllm:8000"
    vllm_model_name: str = "shiritori-llm"
    use_vllm: bool = False
    use_redis_counter: bool = False
    candidate_limit: int = 100
    vllm_timeout_seconds: float = 3.0
    idempotency_ttl_seconds: int = 600
    idempotency_max_entries: int = 10_000
    agent_api_key: SecretStr | None = Field(default=None, min_length=32)
    expose_docs: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
