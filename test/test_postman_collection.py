from app.be.main import create_app
from scripts.generate_postman import (
    create_be_collection,
    create_local_environment,
)


def _flatten_items(items):
    flattened = []
    for item in items:
        if "item" in item:
            flattened.extend(_flatten_items(item["item"]))
        elif item.get("children"):
            flattened.extend(_flatten_items(item["children"]))
        else:
            flattened.append(item)
    return flattened


def test_create_be_collection_uses_base_url_for_http_requests_only():
    schema = create_app().openapi()

    collection = create_be_collection(schema)
    items = _flatten_items(collection["item"])
    raw_urls = {item["request"]["url"]["raw"] for item in items}

    assert collection["info"]["name"] == "Haejillyeok BE"
    assert collection["info"]["schema"] == (
        "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    )
    assert "{{baseUrl}}/api/v1/health" in raw_urls
    assert all("{{baseWs}}" not in raw_url for raw_url in raw_urls)


def test_create_be_collection_excludes_agent_proxy_endpoints():
    schema = create_app().openapi()

    collection = create_be_collection(schema)
    items = _flatten_items(collection["item"])
    raw_urls = {item["request"]["url"]["raw"] for item in items}

    assert "{{baseUrl}}/api/v1/agent/health" not in raw_urls


def test_create_be_collection_leaves_variables_to_environment_file():
    schema = create_app().openapi()

    collection = create_be_collection(schema)

    assert "variable" not in collection


def test_create_be_collection_adds_useful_sample_bodies():
    schema = create_app().openapi()

    collection = create_be_collection(schema)
    items = _flatten_items(collection["item"])
    signup = next(item for item in items if item["name"] == "회원가입")
    create_room = next(item for item in items if item["name"] == "로비 객실 생성")

    assert signup["request"]["body"]["raw"] == (
        "{\n"
        '  "account_id": "{{accountId}}",\n'
        '  "nickname": "{{nickname}}",\n'
        '  "password": "{{password}}"\n'
        "}"
    )
    assert create_room["request"]["body"]["raw"] == (
        "{\n"
        '  "name": "{{roomName}}",\n'
        '  "game_type": "{{gameType}}",\n'
        '  "max_players": {{maxPlayers}}\n'
        "}"
    )


def test_create_be_collection_stores_auth_session_cookie_in_environment():
    schema = create_app().openapi()

    collection = create_be_collection(schema)
    items = _flatten_items(collection["item"])
    login = next(item for item in items if item["name"] == "로그인")
    signup = next(item for item in items if item["name"] == "회원가입")

    for item in (login, signup):
        auth_event = item["event"][0]
        script = "\n".join(auth_event["script"]["exec"])

        assert auth_event["listen"] == "test"
        assert 'pm.environment.set("sessionToken", sessionToken);' in script
        assert "setCookie.match(/session_token=([^;]+)/);" in script


def test_create_local_environment_contains_editable_postman_variables():
    environment = create_local_environment()
    values = {value["key"]: value["value"] for value in environment["values"]}

    assert environment["name"] == "Haejillyeok Local"
    assert values["baseUrl"] == "http://127.0.0.1:8000"
    assert values["baseWs"] == "ws://127.0.0.1:8000"
    assert "baseWsHost" not in values
    assert "baseWsPort" not in values
    assert values["sessionToken"] == ""
    assert values["roomPublicId"] == "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b7e"
    assert values["gameSessionPublicId"] == "018fd0c5-6e1a-7c8e-9b1d-4f99e4a20b80"
    assert values["accountId"] == "player_001"
    assert values["password"] == "secret-password"
    assert values["nickname"] == "초보자"
