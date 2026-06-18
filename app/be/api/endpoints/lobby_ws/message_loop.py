import asyncio
from time import perf_counter

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.be.api.endpoints.lobby_ws.loop_audit import (
    log_lobby_message_completed,
    log_lobby_message_failed,
)
from app.be.api.endpoints.lobby_ws.loop_metrics import (
    record_lobby_inbound_message,
    record_lobby_loop_error,
    record_lobby_message_duration,
    record_lobby_outbound_ping,
)
from app.be.services.lobby import (
    LOBBY_HEARTBEAT_TIMEOUT_SECONDS,
    handle_lobby_message,
    lobby_connection_manager,
    parse_lobby_message,
)
from app.shared.core.exceptions import AppException
from app.shared.core.observability import get_websocket_metrics, start_root_span, start_span


async def run_lobby_message_loop(
    *,
    websocket: WebSocket,
    service_name: str,
    peer: str | None,
    span_attributes: dict[str, str],
) -> int:
    """lobby WebSocket 수신 loop를 실행하고 최종 close code를 반환합니다."""
    metrics = get_websocket_metrics(websocket.app)
    close_code = 1000
    message_started_at: float | None = None
    message_type: str | None = None
    message_payload: object | None = None
    try:
        while True:
            raw_message = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=LOBBY_HEARTBEAT_TIMEOUT_SECONDS,
            )
            message_started_at = perf_counter()
            message = parse_lobby_message(raw_message)
            message_type = message["type"]
            message_payload = message.get("payload")
            message_span_attributes = {**span_attributes, "ws.message.type": message["type"]}
            with start_root_span(
                "WebSocket.lobby.message",
                attributes=message_span_attributes,
            ):
                with start_span("WebSocket.lobby.receive", attributes=message_span_attributes):
                    record_lobby_inbound_message(metrics, message_type=message["type"])
                with start_span("WebSocket.lobby.handle", attributes=message_span_attributes):
                    await handle_lobby_message(
                        manager=lobby_connection_manager,
                        websocket=websocket,
                        message=message,
                    )
            record_lobby_message_duration(
                metrics,
                message_type=message["type"],
                started_at=message_started_at,
            )
            record_lobby_outbound_ping(metrics, source_message_type=message["type"])
            log_lobby_message_completed(
                service_name=service_name,
                peer=peer,
                started_at=message_started_at,
                message_type=message_type,
                payload=message_payload,
            )
    except TimeoutError:
        close_code = 1001
        record_lobby_loop_error(metrics, error_type="heartbeat_timeout")
        await websocket.close(code=1001)
    except WebSocketDisconnect as exc:
        close_code = exc.code
    except AppException as exc:
        close_code = exc.websocket_close_code
        log_lobby_message_failed(
            service_name=service_name,
            peer=peer,
            started_at=message_started_at,
            error_code=str(exc.code),
            close_code=exc.websocket_close_code,
            message_type=message_type,
            payload=message_payload,
        )
        record_lobby_loop_error(metrics, error_type=str(exc.code))
        await lobby_connection_manager.send_error_and_close(websocket, exc)
    return close_code
