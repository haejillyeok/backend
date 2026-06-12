import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.shared.clients.agent import (
    AGENT_API_KEY_HEADER,
    AGENT_HEALTH_PATH,
    AgentClientError,
    AgentClientSettings,
    AgentHealthClient,
)


def build_settings() -> AgentClientSettings:
    return AgentClientSettings(
        agent_url="http://agent.local/",
        k3s_agent_key=SecretStr("a" * 32),
        timeout_seconds=1,
    )


async def test_agent_health_client_maps_plain_health_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://agent.local/api/v1/health"
        assert request.headers[AGENT_API_KEY_HEADER] == "a" * 32
        return httpx.Response(200, json={"status": "ok"})

    client = AgentHealthClient(settings=build_settings(), transport=httpx.MockTransport(handler))

    result = await client.get_health()

    assert result.status == "ok"


async def test_agent_health_client_maps_enveloped_health_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": {"status": "ok"}})

    client = AgentHealthClient(settings=build_settings(), transport=httpx.MockTransport(handler))

    result = await client.get_health()

    assert result.status == "ok"


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(503, json={"status": "down"}), "agent health check failed"),
        (httpx.Response(200, text="not-json"), "agent health check returned invalid json"),
        (httpx.Response(200, json=["ok"]), "agent health check returned invalid payload"),
    ],
)
async def test_agent_health_client_raises_domain_error_for_bad_responses(response, message) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return response

    client = AgentHealthClient(settings=build_settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AgentClientError, match=message):
        await client.get_health()


async def test_agent_health_client_wraps_transport_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = AgentHealthClient(settings=build_settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AgentClientError, match="timed out"):
        await client.get_health()


async def test_agent_health_client_wraps_request_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = AgentHealthClient(settings=build_settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AgentClientError, match="request failed"):
        await client.get_health()


def test_agent_client_settings_normalizes_url_and_rejects_empty_url() -> None:
    assert build_settings().agent_url == "http://agent.local"

    with pytest.raises(ValidationError):
        AgentClientSettings(agent_url="/", k3s_agent_key=SecretStr("a" * 32))


def test_agent_health_path_contract_remains_versioned() -> None:
    assert AGENT_HEALTH_PATH == "/api/v1/health"
