from starlette.datastructures import Headers

from app.shared.core.client_ip import resolve_best_effort_client_ip


def test_resolve_best_effort_client_ip_reads_forwarded_header_first():
    headers = Headers({"forwarded": 'for="203.0.113.9";proto=https'})

    assert resolve_best_effort_client_ip(headers, peer_host="10.0.0.12") == "203.0.113.9"


def test_resolve_best_effort_client_ip_reads_first_x_forwarded_for_ip():
    headers = Headers({"x-forwarded-for": "203.0.113.7, 10.0.0.12"})

    assert resolve_best_effort_client_ip(headers, peer_host="10.0.0.12") == "203.0.113.7"


def test_resolve_best_effort_client_ip_reads_x_real_ip_after_forwarded_headers():
    headers = Headers({"x-real-ip": "198.51.100.4"})

    assert resolve_best_effort_client_ip(headers, peer_host="10.0.0.12") == "198.51.100.4"


def test_resolve_best_effort_client_ip_ignores_invalid_forwarded_values():
    headers = Headers(
        {
            "forwarded": "for=unknown",
            "x-forwarded-for": "not-an-ip",
            "x-real-ip": "also-not-an-ip",
        }
    )

    assert resolve_best_effort_client_ip(headers, peer_host="10.0.0.12") == "10.0.0.12"
