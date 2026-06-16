from time import perf_counter
from typing import Any

from app.be.api.endpoints.lobby_ws.constants import LOBBY_WS_ENDPOINT, LOBBY_WS_ROUTE


def record_lobby_inbound_message(metrics: Any, *, message_type: str) -> None:
    """lobby WebSocket inbound message metric을 기록합니다."""
    metrics.record_message(
        ws_route=LOBBY_WS_ROUTE,
        ws_endpoint=LOBBY_WS_ENDPOINT,
        message_type=message_type,
        direction="inbound",
    )


def record_lobby_message_duration(
    metrics: Any,
    *,
    message_type: str,
    started_at: float,
) -> None:
    """lobby WebSocket message 처리 시간을 기록합니다."""
    metrics.record_message_duration(
        ws_route=LOBBY_WS_ROUTE,
        ws_endpoint=LOBBY_WS_ENDPOINT,
        message_type=message_type,
        duration_seconds=perf_counter() - started_at,
    )


def record_lobby_outbound_ping(metrics: Any, *, source_message_type: str) -> None:
    """lobby ping 요청에 대한 pong outbound metric을 기록합니다."""
    if source_message_type != "ping":
        return
    metrics.record_message(
        ws_route=LOBBY_WS_ROUTE,
        ws_endpoint=LOBBY_WS_ENDPOINT,
        message_type="lobby.pong",
        direction="outbound",
    )


def record_lobby_loop_error(metrics: Any, *, error_type: str) -> None:
    """lobby WebSocket loop에서 발생한 close/error metric을 기록합니다."""
    metrics.record_error(
        ws_route=LOBBY_WS_ROUTE,
        ws_endpoint=LOBBY_WS_ENDPOINT,
        error_type=error_type,
    )
