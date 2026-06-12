from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from app.be.main import create_app


COLLECTION_SCHEMA_URL = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
COLLECTION_NAME = "Haejillyeok BE"
ENVIRONMENT_NAME = "Haejillyeok Local"
DEFAULT_COLLECTION_PATH = Path("postman/haejillyeok-be.postman_collection.json")
DEFAULT_ENVIRONMENT_PATH = Path("postman/haejillyeok-local.postman_environment.json")
OPENAPI_METHODS = ("get", "post", "put", "patch", "delete")

BODY_EXAMPLES = {
    "be_auth_login": {
        "account_id": "{{accountId}}",
        "password": "{{password}}",
    },
    "be_auth_signup": {
        "account_id": "{{accountId}}",
        "nickname": "{{nickname}}",
        "password": "{{password}}",
    },
    "be_game_create_room": {
        "name": "{{roomName}}",
        "game_type": "{{gameType}}",
        "max_players": "{{maxPlayers}}",
    },
}

PATH_VARIABLES = {
    "room_public_id": "roomPublicId",
    "session_public_id": "sessionPublicId",
}

AUTH_SESSION_OPERATION_IDS = {"be_auth_login", "be_auth_signup"}


def create_be_collection(openapi_schema: dict[str, Any]) -> dict[str, Any]:
    """BE OpenAPI schema와 WebSocket 계약으로 Postman collection JSON을 만듭니다."""
    folders: dict[str, list[dict[str, Any]]] = {}

    for path, path_spec in openapi_schema.get("paths", {}).items():
        if _is_excluded_path(path):
            continue
        for method in OPENAPI_METHODS:
            operation = path_spec.get(method)
            if not isinstance(operation, dict):
                continue

            folder_name = _resolve_folder_name(operation)
            folders.setdefault(folder_name, []).append(_create_http_item(path, method, operation))

    folders.setdefault("websocket", []).extend(_create_websocket_items())

    return {
        "info": {
            "name": COLLECTION_NAME,
            "schema": COLLECTION_SCHEMA_URL,
        },
        "item": [
            {"name": folder_name, "item": items}
            for folder_name, items in sorted(folders.items(), key=lambda value: value[0])
        ],
    }


def create_local_environment() -> dict[str, Any]:
    """로컬 BE 서버와 Postman 요청 예시에서 공유할 환경 변수를 만듭니다."""
    return {
        "name": ENVIRONMENT_NAME,
        "values": [
            _environment_value("baseUrl", "http://127.0.0.1:8000"),
            _environment_value("baseWs", "ws://127.0.0.1:8000"),
            _environment_value("sessionToken", ""),
            _environment_value("accountId", "player_001"),
            _environment_value("password", "secret-password"),
            _environment_value("nickname", "초보자"),
            _environment_value("roomName", "첫 객실"),
            _environment_value("gameType", "shiritori"),
            _environment_value("maxPlayers", "4"),
            _environment_value("roomPublicId", "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e"),
            _environment_value("sessionPublicId", "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b80"),
        ],
        "_postman_variable_scope": "environment",
    }


def write_postman_files(
    *,
    collection_path: Path = DEFAULT_COLLECTION_PATH,
    environment_path: Path = DEFAULT_ENVIRONMENT_PATH,
) -> None:
    """현재 BE 앱 계약을 읽어 Postman collection과 environment JSON 파일을 저장합니다."""
    schema = create_app().openapi()
    _write_json(collection_path, create_be_collection(schema))
    _write_json(environment_path, create_local_environment())


def _create_http_item(path: str, method: str, operation: dict[str, Any]) -> dict[str, Any]:
    operation_id = operation.get("operationId", "")
    postman_path = _replace_path_variables(path)
    request: dict[str, Any] = {
        "method": method.upper(),
        "header": _create_headers(path, operation),
        "url": _create_url("{{baseUrl}}", postman_path, operation.get("parameters", [])),
    }

    body = _create_body(operation_id)
    if body is not None:
        request["body"] = body

    description = operation.get("description") or operation.get("summary")
    if description:
        request["description"] = description

    item = {
        "name": operation.get("summary") or operation_id or f"{method.upper()} {path}",
        "request": request,
    }
    if operation_id in AUTH_SESSION_OPERATION_IDS:
        item["event"] = [_create_session_token_test_event()]
    return item


def _create_websocket_items() -> list[dict[str, Any]]:
    return [
        _create_websocket_item(
            name="Realtime WebSocket",
            path="/ws/realtime",
            description=(
                "연결 테스트용 WebSocket입니다. 연결 후 메시지 탭에서 "
                '`{"type":"ping","payload":{"client_time":"2026-06-12T00:00:00Z"}}`를 보냅니다.'
            ),
            requires_session=False,
        ),
        _create_websocket_item(
            name="Lobby Room WebSocket",
            path="/ws/lobby/rooms/{{roomPublicId}}",
            description=(
                "객실 로비 WebSocket입니다. 연결 전에 REST API로 로그인하고 room에 참여해야 합니다. "
                '`{"type":"ping","payload":{"client_time":"2026-06-12T00:00:00Z"}}`를 보냅니다.'
            ),
            requires_session=True,
        ),
    ]


def _create_session_token_test_event() -> dict[str, Any]:
    return {
        "listen": "test",
        "script": {
            "type": "text/javascript",
            "exec": [
                'const setCookie = pm.response.headers.get("Set-Cookie");',
                "if (setCookie) {",
                "  const match = setCookie.match(/session_token=([^;]+)/);",
                "  if (match) {",
                "    const sessionToken = decodeURIComponent(match[1]);",
                '    pm.environment.set("sessionToken", sessionToken);',
                '    console.log("sessionToken environment variable updated.");',
                "  }",
                "}",
            ],
        },
    }


def _create_websocket_item(
    *,
    name: str,
    path: str,
    description: str,
    requires_session: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "request": {
            "method": "GET",
            "header": _session_cookie_header() if requires_session else [],
            "url": _create_url("{{baseWs}}", path),
            "description": description,
        },
    }


def _resolve_folder_name(operation: dict[str, Any]) -> str:
    tags = operation.get("tags")
    if isinstance(tags, list) and tags:
        return str(tags[0])
    return "http"


def _create_headers(path: str, operation: dict[str, Any]) -> list[dict[str, str]]:
    headers = []
    if "requestBody" in operation:
        headers.append({"key": "Content-Type", "value": "application/json"})
    if _requires_session_cookie(path):
        headers.extend(_session_cookie_header())
    return headers


def _session_cookie_header() -> list[dict[str, str]]:
    return [{"key": "Cookie", "value": "session_token={{sessionToken}}"}]


def _requires_session_cookie(path: str) -> bool:
    return path.startswith("/api/v1/game/")


def _is_excluded_path(path: str) -> bool:
    return path.startswith("/api/v1/agent")


def _create_body(operation_id: str) -> dict[str, Any] | None:
    example = BODY_EXAMPLES.get(operation_id)
    if example is None:
        return None
    return {
        "mode": "raw",
        "raw": _json_body(example),
        "options": {"raw": {"language": "json"}},
    }


def _json_body(value: dict[str, Any]) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    return text.replace('"{{maxPlayers}}"', "{{maxPlayers}}")


def _create_url(
    base_variable: str,
    path: str,
    parameters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    url = {
        "raw": f"{base_variable}{path}",
        "host": [base_variable],
        "path": [segment for segment in path.removeprefix("/").split("/") if segment],
    }
    query = [
        {"key": parameter["name"], "value": f"{{{{{_to_lower_camel(parameter['name'])}}}}}"}
        for parameter in parameters or []
        if parameter.get("in") == "query" and parameter.get("name")
    ]
    if query:
        url["query"] = query
    return url


def _replace_path_variables(path: str) -> str:
    return re.sub(
        r"{([^{}]+)}",
        lambda match: f"{{{{{PATH_VARIABLES.get(match.group(1), _to_lower_camel(match.group(1)))}}}}}",
        path,
    )


def _to_lower_camel(value: str) -> str:
    words = value.split("_")
    return words[0] + "".join(word.capitalize() for word in words[1:])


def _environment_value(key: str, value: str) -> dict[str, Any]:
    return {
        "key": key,
        "value": value,
        "type": "default",
        "enabled": True,
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate BE Postman collection JSON files.")
    parser.add_argument("--collection", type=Path, default=DEFAULT_COLLECTION_PATH)
    parser.add_argument("--environment", type=Path, default=DEFAULT_ENVIRONMENT_PATH)
    args = parser.parse_args()

    write_postman_files(collection_path=args.collection, environment_path=args.environment)
    print(f"generated collection: {args.collection}")
    print(f"generated environment: {args.environment}")


if __name__ == "__main__":
    main()
