from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket

from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


RealtimeMessage = dict[str, Any]


class RealtimeConnectionManager:
    """BE WebSocket 연결의 수락, 송신, 해제 상태를 관리합니다.

    주요 입력은 FastAPI `WebSocket` 객체와 JSON envelope 메시지이며, 반환값은 없습니다.
    연결 수락과 active connection registry 변경, WebSocket 송신/종료가 부작용입니다.
    """

    def __init__(self) -> None:
        self._active_connections: set[WebSocket] = set()

    @property
    def connection_count(self) -> int:
        """현재 manager에 등록된 active WebSocket 연결 수를 반환합니다."""
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """WebSocket 연결을 수락하고 active connection registry에 등록합니다."""
        await websocket.accept()
        self._active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """WebSocket 연결을 active connection registry에서 제거합니다."""
        self._active_connections.discard(websocket)

    async def send(self, websocket: WebSocket, message: RealtimeMessage) -> None:
        """특정 WebSocket 연결로 JSON envelope 메시지를 전송합니다."""
        await websocket.send_json(message)

    async def send_error_and_close(self, websocket: WebSocket, error: AppException) -> None:
        """오류 envelope를 전송한 뒤 error definition의 WebSocket close code로 연결을 닫습니다."""
        await websocket.send_json({"type": "error", "payload": error.to_error_payload()})
        await websocket.close(code=error.websocket_close_code)


def parse_realtime_message(raw_message: str) -> RealtimeMessage:
    """WebSocket text frame을 realtime JSON envelope로 파싱하고 검증합니다.

    외부 계약은 `type`과 `payload`를 포함한 JSON object입니다. 계약을 만족하지 않으면
    `VALIDATION_ERROR`로 닫을 수 있도록 `AppException`을 발생시킵니다.
    """
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "json_parse_error"},
        ) from exc

    if not isinstance(message, dict):
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "envelope_must_be_object"},
        )

    message_type = message.get("type")
    payload = message.get("payload")
    if not isinstance(message_type, str) or not isinstance(payload, dict):
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "invalid_envelope"},
        )

    return message


async def handle_realtime_message(
    *,
    manager: RealtimeConnectionManager,
    websocket: WebSocket,
    message: RealtimeMessage,
) -> None:
    """`/api/v1/ws/realtime` WebSocket message type을 처리합니다.

    현재 공개 계약은 연결 확인용 `ping`이며, 같은 payload를 담은 `realtime.pong`을 반환합니다.
    지원하지 않는 message type은 클라이언트가 고칠 수 있는 계약 오류로 보고 연결을 닫습니다.
    """
    if message["type"] == "ping":
        await manager.send(
            websocket,
            {"type": "realtime.pong", "payload": message["payload"]},
        )
        return

    raise AppException(
        code=ErrorCode.VALIDATION_ERROR,
        details={"reason": "unsupported_message_type", "type": message["type"]},
    )


realtime_connection_manager = RealtimeConnectionManager()
