from uuid import UUID


def build_lobby_websocket_path(room_public_id: UUID) -> str:
    """REST 응답에서 클라이언트가 같은 origin으로 연결할 로비 WebSocket path를 만듭니다."""
    return f"/ws/lobby/rooms/{room_public_id}"
