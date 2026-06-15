from dataclasses import dataclass
import json
import logging
from typing import Any
from typing import Literal


AuditPhase = Literal["started", "completed", "failed"]
audit_logger = logging.getLogger("audit.request")
agent_audit_logger = logging.getLogger("audit.agent")
REDACTED_VALUE = "***REDACTED***"
SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "k3s_agent_key",
    "x_agent_api_key",
    "x-agent-api-key",
)


@dataclass(frozen=True)
class AuditEvent:
    protocol: str
    phase: AuditPhase
    service: str
    operation: str
    status_code: str | None = None
    duration_ms: float | None = None
    peer: str | None = None
    error_code: str | None = None
    message_type: str | None = None
    direction: str | None = None
    payload: Any | None = None


def log_audit_event(event: AuditEvent) -> None:
    """요청 감사 이벤트를 안정적인 key=value 형식으로 남깁니다."""
    audit_logger.info(format_audit_event(event))


def format_audit_event(event: AuditEvent) -> str:
    """HTTP/WebSocket 감사 로그에 공통으로 사용할 문자열을 만듭니다."""
    fields = {
        "protocol": event.protocol,
        "phase": event.phase,
        "service": event.service,
        "operation": event.operation,
        "status_code": event.status_code,
        "duration_ms": format_duration_ms(event.duration_ms),
        "peer": event.peer,
        "error_code": event.error_code,
        "message_type": event.message_type,
        "direction": event.direction,
        "payload": format_audit_payload(event.payload),
    }
    parts = [f"{key}={value}" for key, value in fields.items() if value is not None]
    return "audit " + " ".join(parts)


def log_agent_http_event(
    *,
    phase: AuditPhase,
    operation: str,
    status_code: str | None = None,
    duration_ms: float | None = None,
    payload: Any | None = None,
    error_code: str | None = None,
) -> None:
    """BE에서 Agent로 나가는 HTTP 요청/응답을 검열된 payload와 함께 남깁니다."""
    fields = {
        "phase": phase,
        "operation": operation,
        "status_code": status_code,
        "duration_ms": format_duration_ms(duration_ms),
        "error_code": error_code,
        "payload": format_audit_payload(payload),
    }
    parts = [f"{key}={value}" for key, value in fields.items() if value is not None]
    agent_audit_logger.info("agent_http " + " ".join(parts))


def format_duration_ms(duration_ms: float | None) -> str | None:
    """소수점 두 자리 millisecond 문자열을 반환합니다."""
    if duration_ms is None:
        return None
    return f"{duration_ms:.2f}"


def format_audit_payload(payload: Any | None) -> str | None:
    """감사 로그 payload를 민감값 검열 후 한 줄 JSON 문자열로 변환합니다."""
    if payload is None:
        return None
    return json.dumps(
        redact_audit_payload(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def redact_audit_payload(payload: Any) -> Any:
    """로그로 남길 payload에서 token/password/API key 계열 민감값을 재귀적으로 검열합니다."""
    if isinstance(payload, dict):
        return {
            key: REDACTED_VALUE if is_sensitive_audit_key(str(key)) else redact_audit_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_audit_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return [redact_audit_payload(item) for item in payload]
    return payload


def is_sensitive_audit_key(key: str) -> bool:
    """감사 로그에서 값을 숨겨야 하는 key 이름인지 판단합니다."""
    lowered = key.lower()
    normalized = "".join(character if character.isalnum() else "_" for character in lowered)
    compact = normalized.replace("_", "")
    return any(
        part in lowered or part in normalized or part.replace("_", "") in compact
        for part in SENSITIVE_KEY_PARTS
    )
