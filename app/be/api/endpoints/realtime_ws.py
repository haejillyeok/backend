from time import perf_counter

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.be.services.realtime import (
    handle_realtime_message,
    parse_realtime_message,
    realtime_connection_manager,
)
from app.shared.core.audit import AuditEvent, log_audit_event
from app.shared.core.exceptions import AppException


router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/realtime")
async def realtime_websocket(websocket: WebSocket) -> None:
    """BE realtime WebSocket 연결을 열고 JSON envelope 메시지를 처리합니다.

    외부 WebSocket 계약은 `/ws/realtime`이며, HTTPS 운영 환경에서는 같은 path를
    `wss://<host>/ws/realtime`로 연결합니다. 연결 수락과 active registry 등록,
    메시지 송수신, disconnect cleanup이 주요 부작용입니다.
    """
    service_name = websocket.app.title
    peer = websocket.client.host if websocket.client else None
    close_code = 1000
    connected_at = perf_counter()
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="started",
            service=service_name,
            operation="CONNECT /ws/realtime",
            peer=peer,
        )
    )
    await realtime_connection_manager.connect(websocket)
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="completed",
            service=service_name,
            operation="CONNECT /ws/realtime",
            status_code="101",
            duration_ms=(perf_counter() - connected_at) * 1000,
            peer=peer,
        )
    )
    try:
        while True:
            raw_message = await websocket.receive_text()
            message_started_at = perf_counter()
            try:
                message = parse_realtime_message(raw_message)
                await handle_realtime_message(
                    manager=realtime_connection_manager,
                    websocket=websocket,
                    message=message,
                )
            except AppException as exc:
                close_code = exc.websocket_close_code
                log_audit_event(
                    AuditEvent(
                        protocol="websocket",
                        phase="failed",
                        service=service_name,
                        operation="MESSAGE /ws/realtime",
                        status_code=str(exc.websocket_close_code),
                        duration_ms=(perf_counter() - message_started_at) * 1000,
                        peer=peer,
                        error_code=str(exc.code),
                    )
                )
                await realtime_connection_manager.send_error_and_close(websocket, exc)
                return
            log_audit_event(
                AuditEvent(
                    protocol="websocket",
                    phase="completed",
                    service=service_name,
                    operation="MESSAGE /ws/realtime",
                    status_code="200",
                    duration_ms=(perf_counter() - message_started_at) * 1000,
                    peer=peer,
                    message_type=message["type"],
                    direction="inbound",
                    payload=message.get("payload"),
                )
            )
    except WebSocketDisconnect as exc:
        close_code = exc.code
    finally:
        realtime_connection_manager.disconnect(websocket)
        log_audit_event(
            AuditEvent(
                protocol="websocket",
                phase="completed",
                service=service_name,
                operation="DISCONNECT /ws/realtime",
                status_code=str(close_code),
                duration_ms=(perf_counter() - connected_at) * 1000,
                peer=peer,
            )
        )
