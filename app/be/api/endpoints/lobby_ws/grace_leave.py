from fastapi import WebSocket

from app.be.api.endpoints.lobby_ws.constants import LOBBY_WS_ENDPOINT, LOBBY_WS_ROUTE
from app.be.services.game import GameService
from app.be.services.lobby import LobbyDisconnect, lobby_connection_manager
from app.shared.core.observability import get_websocket_metrics, start_span
from app.shared.core.timezone import kst_now, to_kst_isoformat


def schedule_room_leave_after_grace(
    websocket: WebSocket,
    disconnect: LobbyDisconnect,
    game_service: GameService,
) -> None:
    """grace timeout 이후에도 복귀하지 않은 유저를 DB에서 방 퇴장 처리하도록 예약합니다."""

    async def leave_after_grace(disconnect: LobbyDisconnect) -> None:
        with start_span(
            "WebSocket.lobby.grace_leave",
            attributes={
                "ws.route": LOBBY_WS_ROUTE,
                "ws.endpoint": LOBBY_WS_ENDPOINT,
            },
        ):
            result = await game_service.leave_room_after_disconnect_grace(
                room_public_id=disconnect.room_public_id,
                user=disconnect.user,
                left_at=kst_now(),
            )
        if result is None:
            return
        await lobby_connection_manager.broadcast_room(
            result.room_public_id,
            {
                "type": "lobby.room.left",
                "payload": {
                    "room_public_id": str(result.room_public_id),
                    "user_public_id": str(result.user_public_id),
                    "nickname": result.nickname,
                    "left_at": to_kst_isoformat(result.left_at),
                    "remaining_member_count": result.remaining_member_count,
                    "new_owner_user_public_id": (
                        str(result.new_owner_user_public_id)
                        if result.new_owner_user_public_id
                        else None
                    ),
                    "new_owner_nickname": result.new_owner_nickname,
                    "room_closed": result.room_closed,
                },
            },
        )
        metrics = get_websocket_metrics(websocket.app)
        metrics.record_message(
            ws_route=LOBBY_WS_ROUTE,
            ws_endpoint=LOBBY_WS_ENDPOINT,
            message_type="lobby.room.left",
            direction="outbound",
        )

    lobby_connection_manager.schedule_grace_leave(disconnect, leave_after_grace)
