import json
import logging

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.shared.clients.agent import (
    AGENT_API_KEY_HEADER,
    AGENT_ANSWER_PATH,
    AGENT_HEALTH_PATH,
    AgentAnswerClient,
    AgentAnswerRequest,
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


async def test_agent_answer_client_sends_used_words_and_maps_answer_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://agent.local/api/v1/agent/answer"
        assert request.headers[AGENT_API_KEY_HEADER] == "a" * 32
        assert request.method == "POST"
        assert json.loads(request.content) == {
            "request_id": "turn-1",
            "room_id": "session-1",
            "game_type": "word_chain",
            "used_words": ["사과", "과자"],
            "last_char": "자",
            "condition": {"last_char": "자"},
            "ai_policy": {
                "allow_fake_mistake": False,
                "allow_reuse_word": False,
            },
        }
        return httpx.Response(
            200,
            json={
                "request_id": "turn-1",
                "room_id": "session-1",
                "game_type": "word_chain",
                "answer": "자동차",
                "status": "ok",
                "reason": None,
            },
        )

    client = AgentAnswerClient(settings=build_settings(), transport=httpx.MockTransport(handler))

    result = await client.get_answer(
        AgentAnswerRequest(
            request_id="turn-1",
            room_id="session-1",
            game_type="word_chain",
            used_words=["사과", "과자"],
            last_char="자",
            condition={"last_char": "자"},
        )
    )

    assert result.answer == "자동차"
    assert result.status == "ok"


async def test_agent_answer_client_logs_redacted_request_and_response_payloads(caplog) -> None:
    caplog.set_level(logging.INFO, logger="audit.agent")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "turn-1",
                "room_id": "session-1",
                "game_type": "word_chain",
                "answer": "자동차",
                "status": "ok",
                "reason": None,
                "session_token": "agent-should-not-log-this",
            },
        )

    client = AgentAnswerClient(settings=build_settings(), transport=httpx.MockTransport(handler))

    result = await client.get_answer(
        AgentAnswerRequest(
            request_id="turn-1",
            room_id="session-1",
            game_type="word_chain",
            used_words=["사과", "과자"],
            last_char="자",
            condition={"last_char": "자"},
        )
    )

    assert result.answer == "자동차"
    audit_messages = [record.message for record in caplog.records if record.name == "audit.agent"]
    assert any(
        "agent_http phase=started operation=POST /api/v1/agent/answer" in message
        and '"used_words":["사과","과자"]' in message
        and "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" not in message
        for message in audit_messages
    )
    assert any(
        "agent_http phase=completed operation=POST /api/v1/agent/answer status_code=200" in message
        and '"answer":"자동차"' in message
        and "agent-should-not-log-this" not in message
        and '"session_token":"***REDACTED***"' in message
        for message in audit_messages
    )


async def test_agent_answer_client_maps_no_candidate_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "turn-2",
                "room_id": "session-1",
                "game_type": "word_chain",
                "answer": None,
                "status": "no_candidate",
                "reason": "no_available_word",
            },
        )

    client = AgentAnswerClient(settings=build_settings(), transport=httpx.MockTransport(handler))

    result = await client.get_answer(
        AgentAnswerRequest(
            request_id="turn-2",
            room_id="session-1",
            game_type="word_chain",
            used_words=[],
            last_char="힣",
            condition={"last_char": "힣"},
        )
    )

    assert result.answer is None
    assert result.status == "no_candidate"
    assert result.reason == "no_available_word"


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


def test_agent_answer_path_contract_remains_versioned() -> None:
    assert AGENT_ANSWER_PATH == "/api/v1/agent/answer"
