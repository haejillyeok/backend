import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.agent.core.config import AgentSettings
from app.agent.core.security import verify_api_key
from app.agent.main import create_app
from app.agent.prompts import get_shiritori_fallback_prompt


def test_health_does_not_require_api_key() -> None:
    with TestClient(create_app(AgentSettings(agent_api_key="a" * 32))) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_business_api_rejects_missing_api_key() -> None:
    with TestClient(create_app(AgentSettings(agent_api_key="a" * 32))) as client:
        response = client.post(
            "/api/v1/agent/answer",
            json={
                "room_id": "room-1",
                "game_type": "shiritori",
                "used_words": [],
                "last_char": "줄",
            },
        )

    assert response.status_code == 401


def test_openapi_declares_agent_api_key_scheme() -> None:
    schema = create_app(AgentSettings(agent_api_key="a" * 32)).openapi()

    assert schema["components"]["securitySchemes"]["AgentApiKey"] == {
        "type": "apiKey",
        "description": "Backend-to-Agent shared API key.",
        "in": "header",
        "name": "X-Agent-API-Key",
    }


def test_api_key_validation_fails_closed() -> None:
    verify_api_key("a" * 32, SecretStr("a" * 32))

    with pytest.raises(HTTPException) as error:
        verify_api_key("wrong", SecretStr("a" * 32))
    assert error.value.status_code == 401

    with pytest.raises(HTTPException) as error:
        verify_api_key(None, None)
    assert error.value.status_code == 503


def test_shiritori_fallback_prompt_is_variable_based() -> None:
    prompt = get_shiritori_fallback_prompt()

    assert "{start_char}" in prompt
    assert "{used_words}" in prompt
    assert "2글자 이상 4글자 이하" in prompt
