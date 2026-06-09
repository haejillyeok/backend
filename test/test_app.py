import importlib.util
import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

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


def test_shared_exception_carries_http_status_metadata():
    exception = AppException(
        code="TEST_CONFLICT",
        message="테스트 충돌입니다.",
        http_status_code=409,
    )

    assert exception.http_status_code == 409


def test_shared_error_code_registry_exists():
    assert importlib.util.find_spec("app.shared.core.error_codes") is not None


def test_shared_error_definition_maps_http_and_websocket_statuses():
    module = importlib.import_module("app.shared.core.error_codes")

    definition = module.get_error_definition(module.ErrorCode.INVALID_CREDENTIALS)

    assert definition.code is module.ErrorCode.INVALID_CREDENTIALS
    assert definition.type is module.ErrorType.AUTHENTICATION
    assert definition.message == "계정 ID 또는 비밀번호가 올바르지 않습니다."
    assert definition.http_status_code == 401
    assert definition.websocket_close_code == 1008


def test_shared_app_exception_uses_error_definition_defaults():
    from app.shared.core.error_codes import ErrorCode, ErrorType

    exception = AppException(code=ErrorCode.INVALID_CREDENTIALS)

    assert exception.code == "INVALID_CREDENTIALS"
    assert exception.error_type is ErrorType.AUTHENTICATION
    assert exception.message == "계정 ID 또는 비밀번호가 올바르지 않습니다."
    assert exception.http_status_code == 401
    assert exception.websocket_close_code == 1008
    assert exception.to_error_payload() == {
        "success": False,
        "data": None,
        "error": {
            "code": "INVALID_CREDENTIALS",
            "message": "계정 ID 또는 비밀번호가 올바르지 않습니다.",
            "details": None,
        },
    }


def test_shared_openapi_error_response_spec_includes_error_code_example():
    spec = importlib.util.find_spec("app.shared.core.openapi")
    assert spec is not None

    module = importlib.import_module("app.shared.core.openapi")
    response_spec = module.error_response(
        code="INVALID_CREDENTIALS",
        message="계정 ID 또는 비밀번호가 올바르지 않습니다.",
        description="계정 ID의 비밀번호가 일치하지 않음",
    )

    example = response_spec["content"]["application/json"]["example"]
    assert response_spec["model"].__name__ == "ErrorResponse"
    assert example["success"] is False
    assert example["data"] is None
    assert example["error"]["code"] == "INVALID_CREDENTIALS"


def test_shared_openapi_error_responses_spec_supports_multiple_examples():
    module = importlib.import_module("app.shared.core.openapi")
    response_spec = module.error_responses(
        description="인증 실패",
        examples=[
            module.error_example(
                name="invalid_credentials",
                summary="비밀번호 불일치",
                code="INVALID_CREDENTIALS",
                message="계정 ID 또는 비밀번호가 올바르지 않습니다.",
            ),
            module.error_example(
                name="session_expired",
                summary="세션 만료",
                code="SESSION_EXPIRED",
                message="세션이 만료되었습니다.",
            ),
        ],
    )

    examples = response_spec["content"]["application/json"]["examples"]
    assert response_spec["model"].__name__ == "ErrorResponse"
    assert examples["invalid_credentials"]["summary"] == "비밀번호 불일치"
    assert examples["invalid_credentials"]["value"]["error"]["code"] == "INVALID_CREDENTIALS"
    assert examples["session_expired"]["summary"] == "세션 만료"
    assert examples["session_expired"]["value"]["error"]["code"] == "SESSION_EXPIRED"


def test_shared_openapi_groups_error_codes_by_http_status():
    from app.shared.core.error_codes import ErrorCode

    module = importlib.import_module("app.shared.core.openapi")
    responses = module.error_responses_by_status(
        codes=[
            ErrorCode.INVALID_CREDENTIALS,
            ErrorCode.VALIDATION_ERROR,
        ],
    )

    assert set(responses) == {401, 422}
    assert responses[401]["description"] == "Authentication errors"
    assert (
        responses[401]["content"]["application/json"]["examples"]["invalid_credentials"]["value"][
            "error"
        ]["code"]
        == "INVALID_CREDENTIALS"
    )
    assert responses[422]["description"] == "Validation errors"
    assert (
        responses[422]["content"]["application/json"]["examples"]["validation_error"]["value"][
            "error"
        ]["code"]
        == "VALIDATION_ERROR"
    )


def test_be_openapi_documents_success_and_error_envelopes():
    schema = create_be_app().openapi()
    login_operation = schema["paths"]["/api/v1/auth/login"]["post"]

    success_schema_ref = login_operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    success_schema_name = success_schema_ref.removeprefix("#/components/schemas/")
    success_schema = schema["components"]["schemas"][success_schema_name]
    assert success_schema["properties"]["success"]["const"] is True
    assert "error" not in success_schema["properties"]

    invalid_credentials_example = login_operation["responses"]["401"]["content"][
        "application/json"
    ]["examples"]["invalid_credentials"]["value"]
    assert invalid_credentials_example["success"] is False
    assert invalid_credentials_example["data"] is None
    assert invalid_credentials_example["error"]["code"] == "INVALID_CREDENTIALS"
    assert invalid_credentials_example["error"]["details"] is None


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


def test_repository_no_longer_exposes_application_grpc_modules():
    for module_name in (
        "app.be.grpc",
        "app.agent.grpc",
        "app.shared.grpc",
        "app.shared.core.config.grpc",
    ):
        assert importlib.util.find_spec(module_name) is None


def test_project_dependencies_do_not_include_grpc_runtime_packages():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    dependencies = pyproject["project"]["dependencies"]
    dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]
    all_dependencies = [*dependencies, *dev_dependencies]

    assert not any(dependency.startswith(("grpcio", "protobuf")) for dependency in all_dependencies)
    assert "opentelemetry-exporter-otlp-proto-http>=1.39.0" in dependencies
    assert not any("opentelemetry-exporter-otlp-proto-grpc" in item for item in dependencies)
