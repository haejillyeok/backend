from collections.abc import Mapping

from fastapi import WebSocket

from app.be.api.endpoints.match_ws.connection_audit import (
    log_match_connect_completed,
    log_match_disconnect_completed,
)
from app.be.api.endpoints.match_ws.connection_metrics import (
    record_match_connect,
    record_match_disconnect,
    record_match_initial_messages,
)
from app.be.api.endpoints.match_ws.handshake import MatchHandshakeResult
from app.be.services.match import match_connection_manager
from app.shared.core.observability import start_root_span


async def accept_match_connection(
    *,
    websocket: WebSocket,
    handshake: MatchHandshakeResult,
    metrics: object,
    service_name: str,
    peer: str | None,
    connected_at: float,
) -> None:
    """match WebSocket 연결을 manager에 등록하고 초기 event를 전송합니다."""
    await match_connection_manager.connect(
        websocket,
        game_session_public_id=handshake.entry.game_session_public_id,
        participant_id=handshake.participant_id,
        participant=handshake.entry.participant,
    )
    log_match_connect_completed(
        service_name=service_name,
        peer=peer,
        connected_at=connected_at,
    )
    record_match_connect(metrics)
    await match_connection_manager.send_connected(websocket)
    await match_connection_manager.send_snapshot(websocket, handshake.snapshot)
    record_match_initial_messages(metrics)


def disconnect_match_connection(
    *,
    websocket: WebSocket,
    metrics: object,
    service_name: str,
    peer: str | None,
    connected_at: float,
    close_code: int,
    span_attributes: Mapping[str, str],
) -> None:
    """match WebSocket 연결을 manager에서 제거하고 종료 metric/audit을 기록합니다."""
    with start_root_span(
        "WebSocket.match.disconnect",
        attributes={**span_attributes, "ws.close_code": close_code},
    ):
        match_connection_manager.disconnect(websocket)
        record_match_disconnect(
            metrics,
            connected_at=connected_at,
            close_code=close_code,
        )
        log_match_disconnect_completed(
            service_name=service_name,
            peer=peer,
            connected_at=connected_at,
            close_code=close_code,
        )
