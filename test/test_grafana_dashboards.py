import json
from pathlib import Path


DASHBOARD_DIR = Path("docker/grafana/dashboards")


def load_dashboard(filename: str) -> dict:
    return json.loads((DASHBOARD_DIR / filename).read_text(encoding="utf-8"))


def dashboard_text(dashboard: dict) -> str:
    return json.dumps(dashboard, ensure_ascii=False)


def test_dashboard_links_point_to_specific_dashboards() -> None:
    for dashboard_path in DASHBOARD_DIR.glob("*.json"):
        dashboard = load_dashboard(dashboard_path.name)

        for link in dashboard.get("links", []):
            assert link["type"] == "link"
            assert link["url"].startswith("/d/")
            assert "uid" not in link
            assert link.get("tags", []) == []


def test_trace_dashboard_uses_generic_span_filters() -> None:
    dashboard = load_dashboard("fastapi-traces.json")
    text = dashboard_text(dashboard)

    assert "Auth Service Spans" not in text
    assert "Auth Repository Spans" not in text
    assert "AuthService" not in text
    assert "AuthRepository" not in text
    assert "Service Layer Spans" in text
    assert "Repository Layer Spans" in text
    assert 'app.layer=\\"service\\"' in text
    assert 'app.layer=\\"repository\\"' in text


def test_websocket_apm_dashboard_is_generic_and_uses_websocket_metrics() -> None:
    dashboard = load_dashboard("websocket-apm.json")
    text = dashboard_text(dashboard)

    assert dashboard["uid"] == "haejillyeok-websocket-apm"
    assert dashboard["title"] == "Haejillyeok WebSocket APM"
    assert "websocket_connections_active" in text
    assert "websocket_connections_total" in text
    assert "websocket_messages_total" in text
    assert "websocket_errors_total" in text
    assert "websocket_disconnects_total" in text
    assert "websocket_message_duration_seconds_bucket" in text
    assert "$ws_route" in text
    assert "$ws_endpoint" in text
    assert "room_public_id" not in text
    assert "user_public_id" not in text
