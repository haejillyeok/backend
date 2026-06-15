from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.shared.core.observability import start_span


AGENT_API_KEY_HEADER = "X-Agent-API-Key"
AGENT_HEALTH_PATH = "/api/v1/health"
AGENT_ANSWER_PATH = "/api/v1/agent/answer"
DEFAULT_AGENT_TIMEOUT_SECONDS = 3.0
AGENT_HEALTH_SPAN_NAME = "AgentHealthClient.get_health"
AGENT_ANSWER_SPAN_NAME = "AgentAnswerClient.get_answer"


class AgentHealthStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str


class AgentAnswerCondition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    last_char: str | None = None
    chosung: str | None = None
    contains_word: str | None = None


class AgentAnswerPolicy(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    allow_fake_mistake: bool = False
    allow_reuse_word: bool = False


class AgentAnswerRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str | None = None
    room_id: str
    game_type: Literal["word_chain", "chosung", "contains"]
    used_words: list[str]
    last_char: str | None = None
    condition: AgentAnswerCondition | dict[str, str | None] | None = None
    ai_policy: AgentAnswerPolicy = Field(default_factory=AgentAnswerPolicy)


class AgentAnswerResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str | None
    room_id: str
    game_type: Literal["word_chain", "chosung", "contains"]
    answer: str | None
    status: Literal["ok", "no_candidate"]
    reason: str | None = None


class AgentClientSettings(BaseSettings):
    """BE가 Agent 서버를 호출할 때 쓰는 URL과 공유 키를 환경변수에서 읽습니다."""

    agent_url: str = Field(validation_alias="AGENT_URL")
    k3s_agent_key: SecretStr = Field(min_length=32, validation_alias="K3S_AGENT_KEY")
    timeout_seconds: float = DEFAULT_AGENT_TIMEOUT_SECONDS

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    @field_validator("agent_url")
    @classmethod
    def normalize_agent_url(cls, value: str) -> str:
        """base_url 결합이 흔들리지 않도록 뒤쪽 슬래시를 제거합니다."""
        normalized = value.rstrip("/")
        if not normalized:
            raise ValueError("AGENT_URL must not be empty")
        return normalized


class AgentClientError(Exception):
    """Agent 서버 호출 실패를 BE endpoint가 HTTP 오류로 변환할 수 있게 표현합니다."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AgentHealthClient:
    """Agent health API를 호출하고 BE service 계층이 쓰는 모델로 매핑합니다."""

    def __init__(
        self,
        *,
        settings: AgentClientSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def get_health(self) -> AgentHealthStatus:
        """Agent `/api/v1/health`를 호출해 상태 값을 반환합니다.

        요청에는 Agent 비즈니스 API와 같은 `X-Agent-API-Key` 헤더를 넣습니다.
        네트워크 오류, timeout, 4xx/5xx 응답은 `AgentClientError`로 변환합니다.
        """
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.agent_url,
                headers={
                    AGENT_API_KEY_HEADER: self._settings.k3s_agent_key.get_secret_value(),
                },
                timeout=httpx.Timeout(self._settings.timeout_seconds),
                transport=self._transport,
            ) as client:
                with start_span(
                    AGENT_HEALTH_SPAN_NAME,
                    attributes={
                        "app.layer": "client",
                        "peer.service": "haejillyeok-agent",
                        "http.request.method": "GET",
                        "url.path": AGENT_HEALTH_PATH,
                    },
                ) as span:
                    response = await client.get(AGENT_HEALTH_PATH)
                    if hasattr(span, "set_attribute"):
                        span.set_attribute("http.response.status_code", response.status_code)
        except httpx.TimeoutException as exc:
            raise AgentClientError("agent health check timed out") from exc
        except httpx.HTTPError as exc:
            raise AgentClientError("agent health check request failed") from exc

        if response.status_code >= 400:
            raise AgentClientError(
                "agent health check failed",
                status_code=response.status_code,
            )

        return AgentHealthStatus.model_validate(_extract_health_payload(response))


class AgentAnswerClient:
    """Agent answer API를 호출해 AI 턴에 사용할 후보 단어 응답을 반환합니다."""

    def __init__(
        self,
        *,
        settings: AgentClientSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def get_answer(self, payload: AgentAnswerRequest) -> AgentAnswerResult:
        """Agent `/api/v1/agent/answer`를 호출하고 단어 후보 결과로 매핑합니다.

        요청에는 현재 게임에서 이미 사용된 단어 목록과 끝말잇기 조건을 포함합니다. 네트워크 오류,
        timeout, 4xx/5xx 응답은 `AgentClientError`로 변환합니다.
        """
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.agent_url,
                headers={
                    AGENT_API_KEY_HEADER: self._settings.k3s_agent_key.get_secret_value(),
                },
                timeout=httpx.Timeout(self._settings.timeout_seconds),
                transport=self._transport,
            ) as client:
                with start_span(
                    AGENT_ANSWER_SPAN_NAME,
                    attributes={
                        "app.layer": "client",
                        "peer.service": "haejillyeok-agent",
                        "http.request.method": "POST",
                        "url.path": AGENT_ANSWER_PATH,
                    },
                ) as span:
                    response = await client.post(
                        AGENT_ANSWER_PATH,
                        json=payload.model_dump(mode="json"),
                    )
                    if hasattr(span, "set_attribute"):
                        span.set_attribute("http.response.status_code", response.status_code)
        except httpx.TimeoutException as exc:
            raise AgentClientError("agent answer request timed out") from exc
        except httpx.HTTPError as exc:
            raise AgentClientError("agent answer request failed") from exc

        if response.status_code >= 400:
            raise AgentClientError(
                "agent answer request failed",
                status_code=response.status_code,
            )

        return AgentAnswerResult.model_validate(_extract_agent_payload(response, "agent answer"))


def _extract_health_payload(response: httpx.Response) -> dict[str, Any]:
    """Agent health 응답이 plain 또는 envelope여도 상태 모델 입력으로 줄입니다."""
    return _extract_agent_payload(response, "agent health check")


def _extract_agent_payload(response: httpx.Response, label: str) -> dict[str, Any]:
    """Agent 응답이 plain 또는 envelope여도 service 모델 입력으로 줄입니다."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise AgentClientError(
            f"{label} returned invalid json",
            status_code=response.status_code,
        ) from exc

    if isinstance(payload, dict) and payload.get("success") is True:
        data = payload.get("data")
        if isinstance(data, dict):
            return data

    if isinstance(payload, dict):
        return payload

    raise AgentClientError(
        f"{label} returned invalid payload",
        status_code=response.status_code,
    )
