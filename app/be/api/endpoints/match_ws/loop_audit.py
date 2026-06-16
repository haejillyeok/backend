from time import perf_counter

from app.shared.core.audit import AuditEvent, log_audit_event


MATCH_MESSAGE_OPERATION = "MESSAGE /ws/match"


def log_match_message_completed(
    *,
    service_name: str,
    peer: str | None,
    started_at: float,
    message_type: str | None,
    payload: object | None,
) -> None:
    """match WebSocket message 처리가 정상 완료된 audit event를 남깁니다."""
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="completed",
            service=service_name,
            operation=MATCH_MESSAGE_OPERATION,
            status_code="200",
            duration_ms=(perf_counter() - started_at) * 1000,
            peer=peer,
            message_type=message_type,
            direction="inbound",
            payload=payload,
        )
    )


def log_match_message_failed(
    *,
    service_name: str,
    peer: str | None,
    started_at: float | None,
    error_code: str,
    close_code: int,
    message_type: str | None,
    payload: object | None,
) -> None:
    """match WebSocket message 처리 실패를 close code와 함께 audit event로 남깁니다."""
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="failed",
            service=service_name,
            operation=MATCH_MESSAGE_OPERATION,
            status_code=str(close_code),
            duration_ms=(perf_counter() - started_at) * 1000 if started_at is not None else None,
            peer=peer,
            error_code=error_code,
            message_type=message_type,
            direction="inbound",
            payload=payload,
        )
    )
