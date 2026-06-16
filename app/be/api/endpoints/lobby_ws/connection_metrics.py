from time import perf_counter
from typing import Any

from app.be.api.endpoints.lobby_ws.constants import LOBBY_WS_ENDPOINT, LOBBY_WS_ROUTE


def record_lobby_connect_error(metrics: Any, *, error_type: str) -> None:
    """lobby WebSocket 연결 단계에서 발생한 error metric을 기록합니다."""
    metrics.record_error(
        ws_route=LOBBY_WS_ROUTE,
        ws_endpoint=LOBBY_WS_ENDPOINT,
        error_type=error_type,
    )


def record_lobby_connect(metrics: Any) -> None:
    """lobby WebSocket 연결 수립 metric을 기록합니다."""
    metrics.record_connect(ws_route=LOBBY_WS_ROUTE, ws_endpoint=LOBBY_WS_ENDPOINT)


def record_lobby_initial_messages(metrics: Any, *, includes_snapshot: bool) -> None:
    """lobby WebSocket 연결 직후 내려보내는 초기 outbound message metric을 기록합니다."""
    message_types = ["lobby.room.connected"]
    if includes_snapshot:
        message_types.append("lobby.room.snapshot")
    for message_type in message_types:
        metrics.record_message(
            ws_route=LOBBY_WS_ROUTE,
            ws_endpoint=LOBBY_WS_ENDPOINT,
            message_type=message_type,
            direction="outbound",
        )


def record_lobby_disconnect(
    metrics: Any,
    *,
    connected_at: float,
    close_code: int,
) -> None:
    """lobby WebSocket 연결 종료와 유지 시간 metric을 함께 기록합니다."""
    metrics.record_disconnect(
        ws_route=LOBBY_WS_ROUTE,
        ws_endpoint=LOBBY_WS_ENDPOINT,
        close_code=close_code,
    )
    metrics.record_duration(
        ws_route=LOBBY_WS_ROUTE,
        ws_endpoint=LOBBY_WS_ENDPOINT,
        duration_seconds=perf_counter() - connected_at,
        close_code=close_code,
    )
