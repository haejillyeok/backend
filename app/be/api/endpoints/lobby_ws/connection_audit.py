from time import perf_counter

from app.shared.core.audit import AuditEvent, log_audit_event


LOBBY_CONNECT_OPERATION = "CONNECT /ws/lobby/rooms/{room_public_id}"
LOBBY_DISCONNECT_OPERATION = "DISCONNECT /ws/lobby/rooms/{room_public_id}"


def log_lobby_connect_started(*, service_name: str, peer: str | None) -> None:
    """lobby WebSocket 연결 시작 audit event를 남깁니다."""
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="started",
            service=service_name,
            operation=LOBBY_CONNECT_OPERATION,
            peer=peer,
        )
    )


def log_lobby_connect_failed(
    *,
    service_name: str,
    peer: str | None,
    connected_at: float,
    close_code: int,
    error_code: str,
) -> None:
    """lobby WebSocket 연결 실패 audit event를 남깁니다."""
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="failed",
            service=service_name,
            operation=LOBBY_CONNECT_OPERATION,
            status_code=str(close_code),
            duration_ms=(perf_counter() - connected_at) * 1000,
            peer=peer,
            error_code=error_code,
        )
    )


def log_lobby_connect_completed(
    *,
    service_name: str,
    peer: str | None,
    connected_at: float,
) -> None:
    """lobby WebSocket handshake가 완료되어 연결이 수립된 audit event를 남깁니다."""
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="completed",
            service=service_name,
            operation=LOBBY_CONNECT_OPERATION,
            status_code="101",
            duration_ms=(perf_counter() - connected_at) * 1000,
            peer=peer,
        )
    )


def log_lobby_disconnect_completed(
    *,
    service_name: str,
    peer: str | None,
    connected_at: float,
    close_code: int,
) -> None:
    """lobby WebSocket 연결 종료 audit event를 남깁니다."""
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="completed",
            service=service_name,
            operation=LOBBY_DISCONNECT_OPERATION,
            status_code=str(close_code),
            duration_ms=(perf_counter() - connected_at) * 1000,
            peer=peer,
        )
    )
