import importlib.util
import logging
import os
import tomllib
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.agent.main import create_app as create_agent_app
from app.be.dependencies.services import get_current_user
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


def test_shared_kst_clock_returns_timezone_aware_kst_datetime():
    from app.shared.core.timezone import KST, kst_now

    now = kst_now()

    assert now.tzinfo == KST
    assert now.utcoffset().total_seconds() == 9 * 60 * 60


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


def test_be_agent_health_endpoint_returns_agent_status():
    from app.be.dependencies.services import get_agent_health_client
    from app.be.schemas.response.health import HealthResponse

    class FakeAgentHealthClient:
        async def get_health(self) -> HealthResponse:
            return HealthResponse(status="ok")

    app = create_be_app()
    app.dependency_overrides[get_agent_health_client] = lambda: FakeAgentHealthClient()
    client = TestClient(app)

    response = client.get("/api/v1/agent/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "ok"},
    }


def test_be_agent_health_endpoint_maps_agent_failure_to_bad_gateway():
    from app.be.dependencies.services import get_agent_health_client
    from app.shared.clients.agent import AgentClientError

    class FakeAgentHealthClient:
        async def get_health(self):
            raise AgentClientError("agent health check failed", status_code=503)

    app = create_be_app()
    app.dependency_overrides[get_agent_health_client] = lambda: FakeAgentHealthClient()
    client = TestClient(app)

    response = client.get("/api/v1/agent/health")

    assert response.status_code == 502
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {
            "code": "AGENT_HEALTH_UNAVAILABLE",
            "message": "Agent health check failed.",
            "details": {"agent_status_code": 503},
        },
    }


def test_be_game_routes_use_router_level_session_authentication():
    app = create_be_app()
    game_route = _find_api_route(app, "/api/v1/game/rooms/{room_public_id}/start")

    assert any(
        dependency.call is get_current_user and dependency.name is None
        for dependency in game_route.dependant.dependencies
    )


def test_be_public_routes_do_not_use_router_level_session_authentication():
    app = create_be_app()

    for path in (
        "/api/v1/auth/login",
        "/api/v1/auth/signup",
        "/api/v1/health",
        "/api/v1/agent/health",
    ):
        route = _find_api_route(app, path)
        assert all(
            not (dependency.call is get_current_user and dependency.name is None)
            for dependency in route.dependant.dependencies
        )


def _find_api_route(app, path: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path:
            return route
    raise AssertionError(f"route not found: {path}")


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
    signup_operation = schema["paths"]["/api/v1/auth/signup"]["post"]

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

    login_request_ref = login_operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    login_request_schema = schema["components"]["schemas"][
        login_request_ref.removeprefix("#/components/schemas/")
    ]
    assert set(login_request_schema["properties"]) == {"account_id", "password"}

    signup_conflict_example = signup_operation["responses"]["409"]["content"]["application/json"][
        "examples"
    ]["auth_user_conflict"]["value"]
    assert signup_conflict_example["success"] is False
    assert signup_conflict_example["data"] is None
    assert signup_conflict_example["error"]["code"] == "AUTH_USER_CONFLICT"


def test_be_openapi_documents_game_contract_enums():
    schema = create_be_app().openapi()

    create_room_operation = schema["paths"]["/api/v1/game/rooms"]["post"]
    create_room_request_ref = create_room_operation["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    create_room_request = schema["components"]["schemas"][
        create_room_request_ref.removeprefix("#/components/schemas/")
    ]
    game_type_ref = create_room_request["properties"]["game_type"]["$ref"]
    game_type_schema = schema["components"]["schemas"][
        game_type_ref.removeprefix("#/components/schemas/")
    ]
    assert game_type_schema["enum"] == ["word_chain", "chosung", "contains"]

    start_operation = schema["paths"]["/api/v1/game/rooms/{room_public_id}/start"]["post"]
    start_response_ref = start_operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    start_response = schema["components"]["schemas"][
        start_response_ref.removeprefix("#/components/schemas/")
    ]
    start_data_ref = start_response["properties"]["data"]["$ref"]
    start_data = schema["components"]["schemas"][
        start_data_ref.removeprefix("#/components/schemas/")
    ]
    session_status_ref = start_data["properties"]["status"]["$ref"]
    session_status_schema = schema["components"]["schemas"][
        session_status_ref.removeprefix("#/components/schemas/")
    ]
    assert session_status_schema["enum"] == ["starting", "playing", "voting", "result", "aborted"]

    participant_ref = start_data["properties"]["participants"]["items"]["$ref"]
    participant_schema = schema["components"]["schemas"][
        participant_ref.removeprefix("#/components/schemas/")
    ]
    assert set(participant_schema["properties"]) == {"display_name", "seat_number"}


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
            "Origin": "http://localhost:4174",
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


def test_match_service_package_imports_without_annotation_name_errors():
    """Python 3.11 컨테이너에서 annotation 이름 누락으로 앱 import가 깨지지 않게 고정합니다."""
    for module_name in (
        "app.be.services.match",
        "app.be.services.match.ai_turn_followups",
        "app.be.services.match.broadcasters",
        "app.be.services.match.connection_manager",
        "app.be.services.match.message_handler",
        "app.be.services.match.round_events",
        "app.be.services.match.service",
        "app.be.services.match.timers",
        "app.be.services.match.timeout_handlers",
    ):
        assert importlib.import_module(module_name) is not None


def test_match_broadcasters_expose_timeout_and_round_event_modules():
    """match broadcaster는 timeout 처리와 round event 파생 규칙을 별도 모듈로 나눕니다."""
    broadcasters_module = importlib.import_module("app.be.services.match.broadcasters")
    round_events_module = importlib.import_module("app.be.services.match.round_events")
    timeout_handlers_module = importlib.import_module("app.be.services.match.timeout_handlers")

    assert broadcasters_module.round_finished_message_from_turn_resolved is (
        round_events_module.round_finished_message_from_turn_resolved
    )
    assert broadcasters_module.process_match_turn_timeout is (
        timeout_handlers_module.process_match_turn_timeout
    )


def test_match_round_events_expose_message_and_timing_helpers():
    """match round event는 message 변환과 시작 지연 계산을 별도 모듈로 나눕니다."""
    round_events_module = importlib.import_module("app.be.services.match.round_events")
    messages_module = importlib.import_module("app.be.services.match.round_event_messages")
    timing_module = importlib.import_module("app.be.services.match.round_event_timing")

    assert round_events_module.round_finished_message_from_turn_resolved is (
        messages_module.round_finished_message_from_turn_resolved
    )
    assert round_events_module.round_started_message_from_turn_resolved is (
        messages_module.round_started_message_from_turn_resolved
    )
    assert hasattr(timing_module, "seconds_until_round_started")


def test_match_connection_manager_exposes_record_and_message_builders():
    """match connection manager는 연결 record와 event message builder를 별도 모듈로 나눕니다."""
    manager_module = importlib.import_module("app.be.services.match.connection_manager")
    records_module = importlib.import_module("app.be.services.match.connection_records")
    messages_module = importlib.import_module("app.be.services.match.connection_messages")

    assert manager_module.MatchConnection is records_module.MatchConnection
    assert hasattr(messages_module, "match_connected_message")
    assert hasattr(messages_module, "match_snapshot_message")


def test_match_message_handler_exposes_command_modules_and_helpers():
    """match message handler는 parsing, ping, word, vote command handler로 나눕니다."""
    handler_module = importlib.import_module("app.be.services.match.message_handler")
    parsing_module = importlib.import_module("app.be.services.match.message_parsing")
    ping_module = importlib.import_module("app.be.services.match.ping_handler")
    word_module = importlib.import_module("app.be.services.match.word_submit_handler")
    ai_followups_module = importlib.import_module("app.be.services.match.ai_turn_followups")
    vote_module = importlib.import_module("app.be.services.match.vote_submit_handler")
    helpers_module = importlib.import_module("app.be.services.match.message_helpers")

    assert handler_module.parse_match_message is parsing_module.parse_match_message
    assert hasattr(handler_module, "handle_match_message")
    assert hasattr(ping_module, "handle_ping_message")
    assert hasattr(word_module, "handle_word_submit_message")
    assert hasattr(ai_followups_module, "append_ai_turn_if_needed")
    assert hasattr(vote_module, "handle_vote_submit_message")
    assert hasattr(helpers_module, "parse_phase_id")


def test_controller_and_service_dependencies_do_not_own_db_sessions():
    """controller/dependency layer는 DB session을 직접 받거나 rollback하지 않습니다."""
    checked_paths = [
        Path("app/be/dependencies/services.py"),
        Path("app/be/api/endpoints/lobby_ws/connection.py"),
        Path("app/be/api/endpoints/match_ws/connection.py"),
        Path("app/be/api/endpoints/lobby_ws/grace_leave.py"),
    ]

    for path in checked_paths:
        source = path.read_text(encoding="utf-8")
        assert "Depends(get_db_session)" not in source
        assert "AsyncSession" not in source
        assert "db_session.rollback" not in source
        assert "GameRepository(" not in source
        assert "AuthRepository(" not in source
        assert "MatchRepository(" not in source


async def test_match_ai_turn_calls_agent_outside_repository_scope():
    """AI 외부 API 호출은 DB context 조회 transaction 밖에서 수행합니다."""
    from app.be.services.match_ai import AiTurnContext, MatchAiTurnService
    from app.shared.clients.agent import AgentAnswerResult

    state = {"active_repository_scopes": 0, "agent_called_inside_scope": None}
    context = AiTurnContext(
        game_session_public_id=uuid4(),
        phase_id=uuid4(),
        participant_id=uuid4(),
        game_type="word_chain",
        used_words=[],
        required_start_char="가",
    )

    class FakeRepository:
        async def get_ai_turn_context(self, *, game_session_public_id, phase_id):
            assert state["active_repository_scopes"] == 1
            return context

    @asynccontextmanager
    async def repository_scope():
        state["active_repository_scopes"] += 1
        try:
            yield FakeRepository()
        finally:
            state["active_repository_scopes"] -= 1

    class FakeAgentAnswerClient:
        async def get_answer(self, payload):
            state["agent_called_inside_scope"] = state["active_repository_scopes"] > 0
            return AgentAnswerResult(
                request_id=payload.request_id,
                room_id=payload.room_id,
                game_type=payload.game_type,
                answer="가방",
                status="ok",
                reason=None,
            )

    class FakeProgressService:
        async def submit_word(self, **kwargs):
            return None

    service = MatchAiTurnService(
        repository_context_factory=repository_scope,
        agent_answer_client=FakeAgentAnswerClient(),
        progress_service=FakeProgressService(),
    )

    await service.play_ai_turn(
        game_session_public_id=context.game_session_public_id,
        phase_id=context.phase_id,
        now=datetime.now(UTC),
    )

    assert state["agent_called_inside_scope"] is False


def test_game_models_package_exposes_class_modules_and_legacy_imports():
    """게임 ORM 모델은 클래스별 모듈로 나누되 기존 package import를 유지합니다."""
    game_models = importlib.import_module("app.be.models.game")
    room_module = importlib.import_module("app.be.models.game.room")
    valid_word_module = importlib.import_module("app.be.models.game.valid_word")

    assert game_models.Room is room_module.Room
    assert game_models.ValidWord is valid_word_module.ValidWord


def test_game_service_records_package_exposes_class_modules():
    """game service record DTO는 클래스별 모듈로 나누되 기존 records import를 유지합니다."""
    records_package = importlib.import_module("app.be.services.game.records")
    rule_defaults_module = importlib.import_module("app.be.services.game.records.rule_defaults")
    room_record_module = importlib.import_module("app.be.services.game.records.game_room_record")
    room_list_item_module = importlib.import_module(
        "app.be.services.game.records.game_room_list_item"
    )
    room_list_result_module = importlib.import_module(
        "app.be.services.game.records.game_room_list_result"
    )
    lobby_membership_module = importlib.import_module(
        "app.be.services.game.records.current_lobby_membership"
    )
    session_start_module = importlib.import_module(
        "app.be.services.game.records.game_session_start_result"
    )

    assert records_package.default_room_rule_config is (
        rule_defaults_module.default_room_rule_config
    )
    assert records_package.GameRoomRecord is room_record_module.GameRoomRecord
    assert records_package.GameRoomListItem is room_list_item_module.GameRoomListItem
    assert records_package.GameRoomListResult is room_list_result_module.GameRoomListResult
    assert records_package.CurrentLobbyMembership is (
        lobby_membership_module.CurrentLobbyMembership
    )
    assert records_package.GameSessionStartResult is session_start_module.GameSessionStartResult


def test_match_progress_service_package_exposes_records_and_legacy_imports():
    """match progress service는 DTO/protocol/service를 나누되 기존 package import를 유지합니다."""
    match_progress = importlib.import_module("app.be.services.match_progress")
    records_module = importlib.import_module("app.be.services.match_progress.records")
    service_module = importlib.import_module("app.be.services.match_progress.service")

    assert match_progress.MatchBroadcastEvent is records_module.MatchBroadcastEvent
    assert match_progress.MatchProgressService is service_module.MatchProgressService


def test_match_progress_service_exposes_smaller_use_case_mixins_and_payloads():
    """MatchProgressService는 AI 실패, 단어 턴, payload helper를 분리합니다."""
    service_module = importlib.import_module("app.be.services.match_progress.service")
    ai_failure_module = importlib.import_module(
        "app.be.services.match_progress.ai_failure_use_cases"
    )
    word_turn_module = importlib.import_module("app.be.services.match_progress.word_turn_use_cases")
    payloads_module = importlib.import_module(
        "app.be.services.match_progress.turn_resolution_payloads"
    )

    assert hasattr(service_module, "MatchProgressService")
    assert hasattr(ai_failure_module, "MatchProgressAiFailureUseCaseMixin")
    assert hasattr(word_turn_module, "MatchProgressWordTurnUseCaseMixin")
    assert hasattr(payloads_module, "serialize_next_turn")


def test_match_ai_service_package_exposes_context_protocols_and_helpers():
    """match AI service는 context, protocol, helper, service를 분리합니다."""
    match_ai_package = importlib.import_module("app.be.services.match_ai")
    service_module = importlib.import_module("app.be.services.match_ai.service")
    context_module = importlib.import_module("app.be.services.match_ai.context")
    protocols_module = importlib.import_module("app.be.services.match_ai.protocols")
    helpers_module = importlib.import_module("app.be.services.match_ai.rejection_helpers")

    assert match_ai_package.MatchAiTurnService is service_module.MatchAiTurnService
    assert match_ai_package.AiTurnContext is context_module.AiTurnContext
    assert hasattr(protocols_module, "MatchAiTurnRepositoryProtocol")
    assert hasattr(helpers_module, "ai_answer_rejection_reason")


def test_match_vote_service_package_exposes_records_and_legacy_imports():
    """match vote service는 DTO/protocol/service를 나누되 기존 package import를 유지합니다."""
    match_vote = importlib.import_module("app.be.services.match_vote")
    records_module = importlib.import_module("app.be.services.match_vote.records")
    result_events_module = importlib.import_module("app.be.services.match_vote.result_events")
    service_module = importlib.import_module("app.be.services.match_vote.service")
    submission_module = importlib.import_module(
        "app.be.services.match_vote.vote_submission_use_cases"
    )
    timeout_module = importlib.import_module("app.be.services.match_vote.vote_timeout_use_cases")

    assert match_vote.VoteSubmissionRecord is records_module.VoteSubmissionRecord
    assert match_vote.MatchVoteService is service_module.MatchVoteService
    assert hasattr(result_events_module, "result_event_from_vote_record")
    assert hasattr(submission_module, "MatchVoteSubmissionUseCaseMixin")
    assert hasattr(timeout_module, "MatchVoteTimeoutUseCaseMixin")


def test_auth_service_package_exposes_records_errors_and_protocol():
    """auth service는 DTO, 예외, repository protocol, service를 분리합니다."""
    auth_package = importlib.import_module("app.be.services.auth")
    login_module = importlib.import_module("app.be.services.auth.login_use_cases")
    records_module = importlib.import_module("app.be.services.auth.records")
    errors_module = importlib.import_module("app.be.services.auth.errors")
    protocol_module = importlib.import_module("app.be.services.auth.repository_protocol")
    session_module = importlib.import_module("app.be.services.auth.session_use_cases")
    session_result_module = importlib.import_module("app.be.services.auth.session_results")
    service_module = importlib.import_module("app.be.services.auth.service")
    signup_module = importlib.import_module("app.be.services.auth.signup_use_cases")

    assert auth_package.AuthService is service_module.AuthService
    assert auth_package.CurrentUser is records_module.CurrentUser
    assert auth_package.SessionExpiredError is errors_module.SessionExpiredError
    assert hasattr(login_module, "AuthLoginUseCaseMixin")
    assert hasattr(protocol_module, "AuthRepositoryProtocol")
    assert hasattr(session_module, "AuthSessionUseCaseMixin")
    assert hasattr(session_result_module, "AuthSessionResultMixin")
    assert hasattr(signup_module, "AuthSignupUseCaseMixin")


def test_auth_repository_package_exposes_domain_repository():
    """auth repository는 도메인 repository 하나를 노출합니다."""
    auth_repository_package = importlib.import_module("app.be.repository.auth")
    facade_module = importlib.import_module("app.be.repository.auth.repository")

    assert auth_repository_package.AuthRepository is facade_module.AuthRepository
    assert facade_module.AuthRepository.__bases__ == (object,)
    assert hasattr(facade_module.AuthRepository, "get_user_by_account_id")
    assert hasattr(facade_module.AuthRepository, "create_user_session")


def test_auth_endpoint_exposes_cookie_policy_and_response_mappers():
    """auth endpoint는 route, cookie policy, response mapper를 분리합니다."""
    auth_endpoint_module = importlib.import_module("app.be.api.endpoints.auth")
    cookie_module = importlib.import_module("app.be.api.endpoints.auth_cookies")
    mapper_module = importlib.import_module("app.be.api.endpoints.auth_mappers")

    assert hasattr(auth_endpoint_module, "_set_session_cookie")
    assert hasattr(cookie_module, "set_session_cookie")
    assert hasattr(mapper_module, "map_login_response")
    assert hasattr(mapper_module, "map_signup_response")


def test_game_service_package_exposes_facade_and_use_case_mixins():
    """GameService는 facade를 유지하고 room/session/entry use case mixin으로 나눕니다."""
    game_service_package = importlib.import_module("app.be.services.game")
    facade_module = importlib.import_module("app.be.services.game.service")
    room_use_cases = importlib.import_module("app.be.services.game.room_use_cases")
    session_use_cases = importlib.import_module("app.be.services.game.session_use_cases")

    assert game_service_package.GameService is facade_module.GameService
    assert hasattr(room_use_cases, "GameRoomUseCaseMixin")
    assert hasattr(session_use_cases, "GameSessionUseCaseMixin")


def test_game_room_use_cases_expose_smaller_mixins():
    """GameRoomUseCaseMixin은 목록, 설정, 로비 접근, 참여/퇴장 mixin을 조합합니다."""
    room_use_cases = importlib.import_module("app.be.services.game.room_use_cases")
    listing_module = importlib.import_module("app.be.services.game.room_listing_use_cases")
    settings_module = importlib.import_module("app.be.services.game.room_settings_use_cases")
    lobby_module = importlib.import_module("app.be.services.game.room_lobby_use_cases")
    membership_module = importlib.import_module("app.be.services.game.room_member_use_cases")

    assert hasattr(room_use_cases, "GameRoomUseCaseMixin")
    assert hasattr(listing_module, "GameRoomListingUseCaseMixin")
    assert hasattr(settings_module, "GameRoomSettingsUseCaseMixin")
    assert hasattr(lobby_module, "GameRoomLobbyUseCaseMixin")
    assert hasattr(membership_module, "GameRoomMemberUseCaseMixin")


def test_game_membership_use_cases_expose_leave_and_cleanup_mixins():
    """GameMembershipUseCaseMixin은 대기방 퇴장과 로비 이동 cleanup mixin을 조합합니다."""
    membership_module = importlib.import_module("app.be.services.game.membership_use_cases")
    cleanup_module = importlib.import_module("app.be.services.game.lobby_move_cleanup")
    leave_module = importlib.import_module("app.be.services.game.waiting_room_leave")

    assert hasattr(membership_module, "GameMembershipUseCaseMixin")
    assert hasattr(cleanup_module, "GameLobbyMoveCleanupMixin")
    assert hasattr(leave_module, "GameWaitingRoomLeaveMixin")


def test_game_endpoint_package_exposes_router_and_feature_modules():
    """게임 REST endpoint는 router facade와 기능별 모듈로 나눕니다."""
    game_endpoint_package = importlib.import_module("app.be.api.endpoints.game")
    rooms_module = importlib.import_module("app.be.api.endpoints.game.rooms")
    sessions_module = importlib.import_module("app.be.api.endpoints.game.sessions")
    entries_module = importlib.import_module("app.be.api.endpoints.game.entries")
    entry_mappers_module = importlib.import_module("app.be.api.endpoints.game.entry_mappers")
    mappers_module = importlib.import_module("app.be.api.endpoints.game.mappers")
    room_mappers_module = importlib.import_module("app.be.api.endpoints.game.room_mappers")
    session_mappers_module = importlib.import_module("app.be.api.endpoints.game.session_mappers")

    assert hasattr(game_endpoint_package, "router")
    assert hasattr(rooms_module, "router")
    assert hasattr(sessions_module, "router")
    assert hasattr(entries_module, "router")
    assert game_endpoint_package.map_entry_result is mappers_module.map_entry_result
    assert mappers_module.map_entry_result is entry_mappers_module.map_entry_result
    assert mappers_module.map_room_list_item is room_mappers_module.map_room_list_item
    assert mappers_module.map_start_result is session_mappers_module.map_start_result


def test_game_room_endpoint_exposes_smaller_route_modules():
    """게임 room endpoint는 목록, 설정, membership route 모듈로 나눕니다."""
    rooms_module = importlib.import_module("app.be.api.endpoints.game.rooms")
    listing_module = importlib.import_module("app.be.api.endpoints.game.room_listing_routes")
    settings_module = importlib.import_module("app.be.api.endpoints.game.room_settings_routes")
    membership_module = importlib.import_module("app.be.api.endpoints.game.room_membership_routes")

    assert hasattr(rooms_module, "router")
    assert hasattr(listing_module, "router")
    assert hasattr(settings_module, "router")
    assert hasattr(membership_module, "router")


def test_websocket_endpoint_packages_expose_router_and_feature_modules():
    """WebSocket endpoint는 router facade와 연결/메시지 처리 모듈로 나눕니다."""
    match_ws_package = importlib.import_module("app.be.api.endpoints.match_ws")
    match_connection_audit_module = importlib.import_module(
        "app.be.api.endpoints.match_ws.connection_audit"
    )
    match_connection_module = importlib.import_module("app.be.api.endpoints.match_ws.connection")
    match_connection_metrics_module = importlib.import_module(
        "app.be.api.endpoints.match_ws.connection_metrics"
    )
    match_connection_lifecycle_module = importlib.import_module(
        "app.be.api.endpoints.match_ws.connection_lifecycle"
    )
    match_handshake_module = importlib.import_module("app.be.api.endpoints.match_ws.handshake")
    match_loop_audit_module = importlib.import_module("app.be.api.endpoints.match_ws.loop_audit")
    match_loop_metrics_module = importlib.import_module(
        "app.be.api.endpoints.match_ws.loop_metrics"
    )
    match_loop_module = importlib.import_module("app.be.api.endpoints.match_ws.message_loop")
    match_loop_processing_module = importlib.import_module(
        "app.be.api.endpoints.match_ws.loop_message_processing"
    )
    match_loop_timers_module = importlib.import_module("app.be.api.endpoints.match_ws.loop_timers")
    lobby_ws_package = importlib.import_module("app.be.api.endpoints.lobby_ws")
    lobby_connection_audit_module = importlib.import_module(
        "app.be.api.endpoints.lobby_ws.connection_audit"
    )
    lobby_connection_module = importlib.import_module("app.be.api.endpoints.lobby_ws.connection")
    lobby_connection_metrics_module = importlib.import_module(
        "app.be.api.endpoints.lobby_ws.connection_metrics"
    )
    lobby_grace_module = importlib.import_module("app.be.api.endpoints.lobby_ws.grace_leave")
    lobby_loop_audit_module = importlib.import_module("app.be.api.endpoints.lobby_ws.loop_audit")
    lobby_loop_metrics_module = importlib.import_module(
        "app.be.api.endpoints.lobby_ws.loop_metrics"
    )

    assert match_ws_package.match_websocket is match_connection_module.match_websocket
    assert hasattr(match_connection_audit_module, "log_match_connect_started")
    assert hasattr(match_connection_metrics_module, "record_match_initial_messages")
    assert hasattr(match_connection_lifecycle_module, "accept_match_connection")
    assert hasattr(match_connection_lifecycle_module, "disconnect_match_connection")
    assert hasattr(match_handshake_module, "authorize_match_handshake")
    assert hasattr(match_loop_audit_module, "log_match_message_completed")
    assert hasattr(match_loop_metrics_module, "record_match_outbound_messages")
    assert hasattr(match_loop_module, "run_match_message_loop")
    assert hasattr(match_loop_processing_module, "process_match_loop_message")
    assert hasattr(match_loop_timers_module, "next_match_timer_after_broadcasts")
    assert lobby_ws_package.lobby_websocket is lobby_connection_module.lobby_websocket
    assert hasattr(lobby_connection_audit_module, "log_lobby_connect_started")
    assert hasattr(lobby_connection_metrics_module, "record_lobby_initial_messages")
    assert lobby_ws_package.schedule_room_leave_after_grace is (
        lobby_grace_module.schedule_room_leave_after_grace
    )
    assert hasattr(lobby_loop_audit_module, "log_lobby_message_completed")
    assert hasattr(lobby_loop_metrics_module, "record_lobby_outbound_ping")


def test_ws_docs_endpoint_package_exposes_router_and_renderer_modules():
    """WebSocket docs endpoint는 route와 Markdown renderer를 분리합니다."""
    ws_docs_package = importlib.import_module("app.be.api.endpoints.ws_docs")
    routes_module = importlib.import_module("app.be.api.endpoints.ws_docs.routes")
    document_module = importlib.import_module("app.be.api.endpoints.ws_docs.document")
    markdown_helpers_module = importlib.import_module(
        "app.be.api.endpoints.ws_docs.markdown_helpers"
    )
    renderer_module = importlib.import_module("app.be.api.endpoints.ws_docs.renderer")
    markdown_module = importlib.import_module("app.be.api.endpoints.ws_docs.markdown_renderer")
    page_assets_module = importlib.import_module("app.be.api.endpoints.ws_docs.page_assets")

    assert ws_docs_package.router is routes_module.router
    assert ws_docs_package.render_websocket_api_docs is (renderer_module.render_websocket_api_docs)
    assert hasattr(document_module, "render_websocket_docs_page")
    assert hasattr(markdown_helpers_module, "heading_id")
    assert hasattr(markdown_module, "render_markdown_body")
    assert hasattr(page_assets_module, "WEBSOCKET_DOCS_PAGE_STYLE")


def test_lobby_service_package_exposes_manager_records_and_messages():
    """lobby service는 manager, record, message handler를 분리하되 기존 import를 유지합니다."""
    lobby_service_package = importlib.import_module("app.be.services.lobby")
    manager_module = importlib.import_module("app.be.services.lobby.connection_manager")
    connection_messages_module = importlib.import_module(
        "app.be.services.lobby.connection_messages"
    )
    grace_tasks_module = importlib.import_module("app.be.services.lobby.grace_leave_tasks")
    records_module = importlib.import_module("app.be.services.lobby.records")
    messages_module = importlib.import_module("app.be.services.lobby.messages")

    assert lobby_service_package.LobbyConnectionManager is manager_module.LobbyConnectionManager
    assert hasattr(connection_messages_module, "lobby_connected_message")
    assert hasattr(connection_messages_module, "lobby_snapshot_message")
    assert hasattr(grace_tasks_module, "schedule_grace_leave_task")
    assert lobby_service_package.LobbyDisconnect is records_module.LobbyDisconnect
    assert lobby_service_package.handle_lobby_message is messages_module.handle_lobby_message


def test_game_repository_package_exposes_domain_repository_and_service_policies():
    """game repository는 도메인 repository 하나를 노출하고 정책은 service 계층에 둡니다."""
    game_repository = importlib.import_module("app.be.repository.game")
    facade_module = importlib.import_module("app.be.repository.game.repository")
    initial_turn_policy_module = importlib.import_module(
        "app.be.services.game.session_initial_turn_policy"
    )

    assert game_repository.GameRepository is facade_module.GameRepository
    assert facade_module.GameRepository.__bases__ == (object,)
    assert hasattr(initial_turn_policy_module, "SessionInitialTurnPolicy")


def test_game_repository_exposes_db_step_methods_without_session_flow_methods():
    """game repository는 DB 실행 단위 메서드를 노출하고 session flow는 service가 조합합니다."""
    facade_module = importlib.import_module("app.be.repository.game.repository")

    assert hasattr(facade_module.GameRepository, "get_active_game_session_for_room")
    assert hasattr(facade_module.GameRepository, "create_game_session_row")
    assert hasattr(facade_module.GameRepository, "create_session_participant_row")
    assert hasattr(facade_module.GameRepository, "create_session_phase_row")
    assert hasattr(facade_module.GameRepository, "create_word_turn_row")
    assert not hasattr(facade_module.GameRepository, "create_game_session")


def test_match_vote_repository_package_exposes_domain_repository_and_service_policies():
    """match vote repository는 도메인 repository 하나를 노출하고 정책은 service 계층에 둡니다."""
    match_vote_repository = importlib.import_module("app.be.repository.match_vote")
    facade_module = importlib.import_module("app.be.repository.match_vote.repository")
    result_policy_module = importlib.import_module("app.be.services.match_vote.result_policy")
    vote_policy_module = importlib.import_module("app.be.services.match_vote.vote_policy")

    assert match_vote_repository.MatchVoteRepository is facade_module.MatchVoteRepository
    assert hasattr(result_policy_module, "MatchVoteResultPolicy")
    assert hasattr(vote_policy_module, "MatchVotePolicy")


def test_match_repository_package_exposes_domain_repository():
    """match repository는 도메인 repository 하나를 노출하고 snapshot 조립은 service가 담당합니다."""
    match_repository = importlib.import_module("app.be.repository.match")
    facade_module = importlib.import_module("app.be.repository.match.repository")

    assert match_repository.MatchRepository is facade_module.MatchRepository
    assert facade_module.MatchRepository.__bases__ == (object,)
    assert hasattr(facade_module.MatchRepository, "get_game_session")
    assert hasattr(facade_module.MatchRepository, "list_participants")
    assert hasattr(facade_module.MatchRepository, "list_score_totals")
    assert not hasattr(facade_module.MatchRepository, "get_snapshot")


def test_match_progress_repository_package_exposes_facade_and_helper_modules():
    """match progress repository는 도메인 repository facade와 단일 class를 유지합니다."""
    match_progress_repository = importlib.import_module("app.be.repository.match_progress")
    facade_module = importlib.import_module("app.be.repository.match_progress.repository")

    assert (
        match_progress_repository.MatchProgressRepository is facade_module.MatchProgressRepository
    )
    assert hasattr(facade_module.MatchProgressRepository, "get_game_session")
    assert hasattr(facade_module.MatchProgressRepository, "create_word_submit_action")
    assert not hasattr(facade_module.MatchProgressRepository, "record_word_submission")
    assert not hasattr(facade_module.MatchProgressRepository, "record_turn_timeout")


def test_match_progress_word_actions_expose_submission_and_rejection_mixins():
    """match progress 단어 진행 정책은 service 계층 모듈에서 관리합니다."""
    submission_policy_module = importlib.import_module(
        "app.be.services.match_progress.word_submission_policy"
    )
    turn_policy_module = importlib.import_module("app.be.services.match_progress.turn_policy")
    round_transition_module = importlib.import_module(
        "app.be.services.match_progress.round_transition_policy"
    )
    turn_drafts_module = importlib.import_module("app.be.services.match_progress.word_turn_drafts")

    assert hasattr(submission_policy_module, "WordSubmissionPolicy")
    assert hasattr(turn_policy_module, "MatchProgressTurnPolicy")
    assert hasattr(round_transition_module, "MatchProgressRoundTransitionPolicy")
    assert hasattr(turn_drafts_module, "NextWordTurnDraft")


def test_match_progress_repository_injects_word_submission_policy():
    """match progress service는 단어/턴/라운드 전환 정책을 교체할 수 있게 주입받습니다."""
    service_module = importlib.import_module("app.be.services.match_progress.service")
    submission_policy_module = importlib.import_module(
        "app.be.services.match_progress.word_submission_policy"
    )
    turn_policy_module = importlib.import_module("app.be.services.match_progress.turn_policy")
    round_transition_module = importlib.import_module(
        "app.be.services.match_progress.round_transition_policy"
    )

    submission_policy = submission_policy_module.WordSubmissionPolicy()
    turn_policy = turn_policy_module.MatchProgressTurnPolicy()
    round_transition_policy = round_transition_module.MatchProgressRoundTransitionPolicy()
    service = service_module.MatchProgressService(
        object(),
        round_transition_policy=round_transition_policy,
        turn_policy=turn_policy,
        word_submission_policy=submission_policy,
    )

    assert service.round_transition_policy is round_transition_policy
    assert service.turn_policy is turn_policy
    assert service.word_submission_policy is submission_policy


def test_server_layer_packages_are_owned_by_each_server():
    for module_name in (
        "app.be.dependencies",
        "app.be.repository",
        "app.be.schemas",
        "app.be.services",
        "app.agent.dependencies",
        "app.agent.repository",
        "app.agent.schemas",
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
