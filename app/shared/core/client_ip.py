from collections.abc import Mapping
from ipaddress import ip_address


def resolve_best_effort_client_ip(
    headers: Mapping[str, str],
    *,
    peer_host: str | None,
) -> str | None:
    """Forwarded 계열 헤더와 peer 주소에서 기록용 클라이언트 IP를 고릅니다.

    주요 입력은 HTTP headers와 ASGI peer host입니다. 반환값은 유효한 IP 문자열 또는 `None`이며,
    신뢰 프록시 검증을 하지 않으므로 보안 판단이 아니라 best-effort 접속 기록에만 사용합니다.
    """
    for candidate in _iter_forwarded_candidates(headers):
        normalized_ip = _normalize_ip(candidate)
        if normalized_ip is not None:
            return normalized_ip

    return _normalize_ip(peer_host)


def _iter_forwarded_candidates(headers: Mapping[str, str]) -> list[str]:
    candidates: list[str] = []

    forwarded = _get_header(headers, "forwarded")
    if forwarded:
        candidates.extend(_parse_forwarded_header(forwarded))

    x_forwarded_for = _get_header(headers, "x-forwarded-for")
    if x_forwarded_for:
        candidates.extend(part.strip() for part in x_forwarded_for.split(","))

    x_real_ip = _get_header(headers, "x-real-ip")
    if x_real_ip:
        candidates.append(x_real_ip.strip())

    return candidates


def _parse_forwarded_header(header_value: str) -> list[str]:
    candidates: list[str] = []
    for forwarded_entry in header_value.split(","):
        for parameter in forwarded_entry.split(";"):
            name, separator, value = parameter.strip().partition("=")
            if separator and name.lower() == "for":
                candidates.append(value.strip())
                break
    return candidates


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    value = headers.get(name)
    if value is not None:
        return value

    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def _normalize_ip(candidate: str | None) -> str | None:
    if candidate is None:
        return None

    value = candidate.strip().strip('"')
    if not value:
        return None

    if value.startswith("["):
        value = value.partition("]")[0].removeprefix("[")
    elif value.count(":") == 1:
        host, separator, port = value.partition(":")
        if separator and port.isdecimal():
            value = host

    try:
        return str(ip_address(value))
    except ValueError:
        return None
