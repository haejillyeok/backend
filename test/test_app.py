import importlib.util

from fastapi.testclient import TestClient
from grpc import StatusCode

from app.agent.main import create_app as create_agent_app
from app.be.main import create_app as create_be_app
from app.shared.core.exceptions import AppException
from app.shared.core.responses import fail, ok


def test_be_health_endpoints_return_ok():
    client = TestClient(create_be_app())

    root_response = client.get("/health")
    api_response = client.get("/api/v1/health")

    assert root_response.status_code == 200
    assert root_response.json() == {"status": "ok"}
    assert api_response.status_code == 200
    assert api_response.json() == {
        "success": True,
        "data": {"status": "ok"},
        "error": None,
    }


def test_be_custom_exception_returns_common_error_response():
    app = create_be_app()

    @app.get("/api/v1/test-error")
    def raise_test_error():
        raise AppException(
            code="TEST_CONFLICT",
            message="테스트 충돌입니다.",
            details={"field": "nickname"},
            http_status_code=409,
            grpc_status_code=StatusCode.ALREADY_EXISTS,
        )

    client = TestClient(app)

    response = client.get("/api/v1/test-error")

    assert response.status_code == 409
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {
            "code": "TEST_CONFLICT",
            "message": "테스트 충돌입니다.",
            "details": {"field": "nickname"},
        },
    }


def test_shared_envelope_can_be_used_at_protocol_boundaries():
    success = ok({"status": "ok"})
    error = fail(
        code="TEST_CONFLICT",
        message="테스트 충돌입니다.",
        details={"field": "nickname"},
    )

    assert success.model_dump(mode="json") == {
        "success": True,
        "data": {"status": "ok"},
        "error": None,
    }
    assert error.model_dump(mode="json") == {
        "success": False,
        "data": None,
        "error": {
            "code": "TEST_CONFLICT",
            "message": "테스트 충돌입니다.",
            "details": {"field": "nickname"},
        },
    }


def test_shared_exception_carries_http_and_grpc_status_metadata():
    exception = AppException(
        code="TEST_CONFLICT",
        message="테스트 충돌입니다.",
        http_status_code=409,
        grpc_status_code=StatusCode.ALREADY_EXISTS,
    )

    assert exception.http_status_code == 409
    assert exception.grpc_status_code is StatusCode.ALREADY_EXISTS


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
