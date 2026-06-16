from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any

from app.be.api.endpoints.match_ws.constants import MATCH_WS_ENDPOINT, MATCH_WS_ROUTE


def record_match_inbound_message(metrics: Any, *, message_type: str) -> None:
    """match WebSocket inbound message metric을 기록합니다."""
    metrics.record_message(
        ws_route=MATCH_WS_ROUTE,
        ws_endpoint=MATCH_WS_ENDPOINT,
        message_type=message_type,
        direction="inbound",
    )


def record_match_message_duration(
    metrics: Any,
    *,
    message_type: str,
    started_at: float,
) -> None:
    """match WebSocket message 처리 시간을 기록합니다."""
    metrics.record_message_duration(
        ws_route=MATCH_WS_ROUTE,
        ws_endpoint=MATCH_WS_ENDPOINT,
        message_type=message_type,
        duration_seconds=perf_counter() - started_at,
    )


def record_match_outbound_messages(
    metrics: Any,
    *,
    source_message_type: str,
    broadcast_messages: Sequence[Mapping[str, object]],
) -> None:
    """match WebSocket message 처리 중 발생한 outbound message metric을 기록합니다."""
    if source_message_type == "ping":
        metrics.record_message(
            ws_route=MATCH_WS_ROUTE,
            ws_endpoint=MATCH_WS_ENDPOINT,
            message_type="match.pong",
            direction="outbound",
        )
    for broadcast_message in broadcast_messages:
        broadcast_message_type = broadcast_message.get("type")
        if not isinstance(broadcast_message_type, str):
            continue
        metrics.record_message(
            ws_route=MATCH_WS_ROUTE,
            ws_endpoint=MATCH_WS_ENDPOINT,
            message_type=broadcast_message_type,
            direction="outbound",
        )


def record_match_loop_error(metrics: Any, *, error_type: str) -> None:
    """match WebSocket loop에서 발생한 close/error metric을 기록합니다."""
    metrics.record_error(
        ws_route=MATCH_WS_ROUTE,
        ws_endpoint=MATCH_WS_ENDPOINT,
        error_type=error_type,
    )
