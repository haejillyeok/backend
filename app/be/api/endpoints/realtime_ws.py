from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.be.services.realtime import (
    handle_realtime_message,
    parse_realtime_message,
    realtime_connection_manager,
)
from app.shared.core.exceptions import AppException


router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/realtime")
async def realtime_websocket(websocket: WebSocket) -> None:
    """BE realtime WebSocket 연결을 열고 JSON envelope 메시지를 처리합니다.

    외부 WebSocket 계약은 `/api/v1/ws/realtime`이며, HTTPS 운영 환경에서는 같은 path를
    `wss://<host>/api/v1/ws/realtime`로 연결합니다. 연결 수락과 active registry 등록,
    메시지 송수신, disconnect cleanup이 주요 부작용입니다.
    """
    await realtime_connection_manager.connect(websocket)
    try:
        while True:
            raw_message = await websocket.receive_text()
            message = parse_realtime_message(raw_message)
            await handle_realtime_message(
                manager=realtime_connection_manager,
                websocket=websocket,
                message=message,
            )
    except WebSocketDisconnect:
        pass
    except AppException as exc:
        await realtime_connection_manager.send_error_and_close(websocket, exc)
    finally:
        realtime_connection_manager.disconnect(websocket)
