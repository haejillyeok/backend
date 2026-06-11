import importlib.util
import logging
import os
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.main import create_app as create_agent_app
from app.be.main import create_app as create_be_app
from app.shared.core import logging_config
from app.shared.core.config import AppSettings, configure_app_timezone
from app.shared.core.exceptions import AppException
from app.shared.core.logging_config import (
    LogFileSettings,
    cleanup_log_files,
    configure_logging,
    remove_project_file_handlers,
)
from app.shared.core.observability import resolve_otlp_http_endpoint
from app.shared.core.route_guard import mark_blocked_access_log_path
from app.shared.core.responses import fail, ok


def test_app_settings_defaults_to_kst_timezone(monkeypatch):
    monkeypatch.delenv("APP_TIMEZONE", raising=False)

    settings = AppSettings(app_name="test")

    assert settings.timezone == "Asia/Seoul"


def test_configure_app_timezone_sets_process_timezone(monkeypatch):
    monkeypatch.delenv("TZ", raising=False)

    configure_app_timezone("Asia/Seoul")

    assert os.environ["TZ"] == "Asia/Seoul"


def test_log_file_settings_read_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_FILE_ENABLED", "false")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "app-logs"))
    monkeypatch.setenv("LOG_RETENTION_DAYS", "7")
    monkeypatch.setenv("LOG_MAX_TOTAL_BYTES", "2048")
    monkeypatch.setenv("LOG_CLEANUP_INTERVAL_SECONDS", "30")

    settings = LogFileSettings.from_environment()

    assert settings.enabled is False
    assert settings.directory == tmp_path / "app-logs"
    assert settings.retention_days == 7
    assert settings.max_total_bytes == 2048
    assert settings.cleanup_interval_seconds == 30


def test_cleanup_log_files_deletes_old_and_excess_files(tmp_path):
    old_log = tmp_path / "haejillyeok-be.log.2026-05-01"
    larger_log = tmp_path / "haejillyeok-be.log.2026-06-01"
    newer_log = tmp_path / "haejillyeok-be.log"
    ignored_file = tmp_path / "notes.txt"

    old_log.write_text("old", encoding="utf-8")
    larger_log.write_text("x" * 8, encoding="utf-8")
    newer_log.write_text("y" * 4, encoding="utf-8")
    ignored_file.write_text("keep", encoding="utf-8")

    old_timestamp = (datetime.now(UTC) - timedelta(days=15)).timestamp()
    larger_timestamp = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    newer_timestamp = (datetime.now(UTC) - timedelta(days=1)).timestamp()
    os.utime(old_log, (old_timestamp, old_timestamp))
    os.utime(larger_log, (larger_timestamp, larger_timestamp))
    os.utime(newer_log, (newer_timestamp, newer_timestamp))

    cleanup_log_files(tmp_path, retention_days=14, max_total_bytes=6)

    assert not old_log.exists()
    assert not larger_log.exists()
    assert newer_log.exists()
    assert ignored_file.exists()


def test_cleanup_log_files_keeps_protected_active_log(tmp_path):
    active_log = tmp_path / "haejillyeok-be.log"
    older_log = tmp_path / "haejillyeok-be.log.2026-06-01"

    active_log.write_text("x" * 8, encoding="utf-8")
    older_log.write_text("y" * 8, encoding="utf-8")

    active_timestamp = (datetime.now(UTC) - timedelta(days=3)).timestamp()
    older_timestamp = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    os.utime(active_log, (active_timestamp, active_timestamp))
    os.utime(older_log, (older_timestamp, older_timestamp))

    cleanup_log_files(
        tmp_path,
        retention_days=14,
        max_total_bytes=6,
        protected_paths={active_log},
    )

    assert active_log.exists()
    assert not older_log.exists()


def test_configure_logging_writes_uvicorn_logs_to_file(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_FILE_ENABLED", "true")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    configure_logging("test-app", environment="prod")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.info("GET /health 200")
    for handler in logging.getLogger().handlers + uvicorn_access_logger.handlers:
        handler.flush()

    log_text = (tmp_path / "test-app.log").read_text(encoding="utf-8")

    assert "[test-app] [app.shared.core.logging_config] File logging configured" in log_text
    assert "[test-app] [uvicorn.access] GET /health 200" in log_text
    remove_project_file_handlers(
        logging.getLogger(),
        logging.getLogger("uvicorn"),
        logging.getLogger("uvicorn.access"),
    )


def test_configure_logging_filters_blocked_route_access_logs(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_FILE_ENABLED", "true")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    configure_logging("test-app", environment="prod")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    mark_blocked_access_log_path("/.env")
    uvicorn_access_logger.info(
        '%s - "%s %s HTTP/%s" %d',
        "testclient",
        "GET",
        "/.env",
        "1.1",
        404,
    )
    uvicorn_access_logger.info(
        '%s - "%s %s HTTP/%s" %d',
        "testclient",
        "GET",
        "/health",
        "1.1",
        200,
    )
    for handler in logging.getLogger().handlers + uvicorn_access_logger.handlers:
        handler.flush()

    log_text = (tmp_path / "test-app.log").read_text(encoding="utf-8")

    assert "/.env" not in log_text
    assert "/health" in log_text
    remove_project_file_handlers(
        logging.getLogger(),
        logging.getLogger("uvicorn"),
        logging.getLogger("uvicorn.access"),
    )


def test_configure_logging_reports_file_setup_failure(monkeypatch, tmp_path, caplog):
    def raise_permission_error(*args, **kwargs):
        raise PermissionError("read-only log directory")

    monkeypatch.setenv("LOG_FILE_ENABLED", "true")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setattr(
        logging_config,
        "ManagedTimedRotatingFileHandler",
        raise_permission_error,
    )
    caplog.set_level(logging.ERROR, logger="app.shared.core.logging_config")

    configure_logging("test-app", environment="prod")

    assert "File logging setup failed path=" in caplog.text
    assert "Continuing with stdout logging only." in caplog.text


def test_resolve_otlp_http_endpoint_appends_signal_path_to_base_endpoint():
    assert (
        resolve_otlp_http_endpoint("http://localhost:4318", signal_path="/v1/metrics")
        == "http://localhost:4318/v1/metrics"
    )
    assert (
        resolve_otlp_http_endpoint("http://otel-collector:4318", signal_path="/v1/traces")
        == "http://otel-collector:4318/v1/traces"
    )


def test_resolve_otlp_http_endpoint_replaces_signal_specific_path():
    assert (
        resolve_otlp_http_endpoint("http://localhost:4318/v1/metrics", signal_path="/v1/traces")
        == "http://localhost:4318/v1/traces"
    )


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


def test_be_openapi_description_links_websocket_api_docs():
    schema = create_be_app().openapi()

    description = schema["info"]["description"]

    assert "[WebSocket API 문서](/ws-docs)" in description


def test_be_keeps_fastapi_documentation_routes_open():
    client = TestClient(create_be_app())

    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path)

        assert response.status_code == 200


def test_agent_health_endpoints_return_ok():
    client = TestClient(create_agent_app())

    for path in ("/health", "/api/v1/health"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_be_allows_configured_cors_origins_for_preflight():
    allowed_origins = [
        "http://localhost:3000",
        "https://haejillyeok.com",
        "https://agent.haejillyeok.com",
        "https://www.haejillyeok.com",
    ]
    client = TestClient(create_be_app())

    for origin in allowed_origins:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"
        assert "GET" in response.headers["access-control-allow-methods"]


def test_be_rejects_unconfigured_cors_origin_for_preflight():
    client = TestClient(create_be_app())

    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://front.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_agent_does_not_install_cors_middleware():
    client = TestClient(create_agent_app())

    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


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
