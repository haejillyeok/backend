import importlib.util

from fastapi.testclient import TestClient

from app.agent.main import create_app as create_agent_app
from app.be.main import create_app as create_be_app


def test_be_health_endpoints_return_ok():
    client = TestClient(create_be_app())

    for path in ("/health", "/api/v1/health"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_agent_health_endpoints_return_ok():
    client = TestClient(create_agent_app())

    for path in ("/health", "/api/v1/health"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_be_and_agent_have_separate_app_titles():
    be_app = create_be_app()
    agent_app = create_agent_app()

    assert be_app.title == "haejillyeok-be"
    assert agent_app.title == "haejillyeok-agent"


def test_shared_package_does_not_expose_schemas():
    assert importlib.util.find_spec("app.shared.schemas") is None


def test_server_layer_packages_are_owned_by_each_server():
    for module_name in (
        "app.be.dependencies",
        "app.be.repository",
        "app.be.schemas",
        "app.be.services",
        "app.agent.dependencies",
        "app.agent.services",
        "app.shared.core",
    ):
        assert importlib.util.find_spec(module_name) is not None

    for module_name in (
        "app.core",
        "app.dependencies",
        "app.repository",
        "app.schemas",
        "app.services",
        "app.utils",
        "app.agent.repository",
        "app.agent.schemas",
    ):
        assert importlib.util.find_spec(module_name) is None
