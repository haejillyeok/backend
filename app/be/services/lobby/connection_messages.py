from app.be.services.game import RoomLobbySnapshotResult
from app.be.services.lobby.records import LobbyConnection, LobbyMessage
from app.shared.core.timezone import to_kst_isoformat


def lobby_connected_message(connection: LobbyConnection) -> LobbyMessage:
    """로비 연결 직후 room 구독과 user identity를 확인할 `lobby.room.connected` event를 조립합니다."""
    return {
        "type": "lobby.room.connected",
        "payload": {
            "room_public_id": connection.room_public_id,
            "user": {
                "public_id": connection.user.public_id,
                "account_id": connection.user.account_id,
                "nickname": connection.user.nickname,
            },
        },
    }


def lobby_snapshot_message(snapshot: RoomLobbySnapshotResult) -> LobbyMessage:
    """로비 화면 초기화에 필요한 활성 멤버 `lobby.room.snapshot` event를 조립합니다."""
    return {
        "type": "lobby.room.snapshot",
        "payload": {
            "room_public_id": snapshot.room_public_id,
            "owner_user_public_id": snapshot.owner_user_public_id,
            "members": [
                {
                    "user_public_id": member.user_public_id,
                    "nickname": member.nickname,
                    "is_owner": member.is_owner,
                    "joined_at": to_kst_isoformat(member.joined_at),
                }
                for member in snapshot.members
            ],
        },
    }
