from dataclasses import dataclass
import logging
from typing import Literal


AuditPhase = Literal["started", "completed", "failed"]
audit_logger = logging.getLogger("audit.request")


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


def log_audit_event(event: AuditEvent) -> None:
    """요청 감사 이벤트를 안정적인 key=value 형식으로 남깁니다."""
    audit_logger.info(format_audit_event(event))


def format_audit_event(event: AuditEvent) -> str:
    """HTTP 요청 감사 로그에 공통으로 사용할 문자열을 만듭니다."""
    fields = {
        "protocol": event.protocol,
        "phase": event.phase,
        "service": event.service,
        "operation": event.operation,
        "status_code": event.status_code,
        "duration_ms": format_duration_ms(event.duration_ms),
        "peer": event.peer,
        "error_code": event.error_code,
    }
    parts = [f"{key}={value}" for key, value in fields.items() if value is not None]
    return "audit " + " ".join(parts)


def format_duration_ms(duration_ms: float | None) -> str | None:
    """소수점 두 자리 millisecond 문자열을 반환합니다."""
    if duration_ms is None:
        return None
    return f"{duration_ms:.2f}"
