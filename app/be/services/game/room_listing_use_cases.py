from uuid import UUID

from app.be.services.game.records import (
    CurrentLobbyMembership,
    GameRoomListResult,
    WAITING_ROOM_STATUS,
)

from app.be.services.game.paths import build_lobby_websocket_path


class GameRoomListingUseCaseMixin:
    async def list_rooms(self, *, user_id: UUID) -> GameRoomListResult:
        """로비 화면에서 선택할 수 있는 객실과 현재 참여 중인 유효 로비를 반환합니다."""
        async with self.repository_scope():
            return await self._list_rooms(user_id=user_id)

    async def _list_rooms(self, *, user_id: UUID) -> GameRoomListResult:
        """객실 목록 조회 transaction 안에서 현재 로비 정보를 조립합니다."""
        rooms = await self.repository.list_rooms(user_id=user_id)
        current_room = next(
            (
                room
                for room in rooms
                if room.is_current_user_member and room.status == WAITING_ROOM_STATUS
            ),
            None,
        )
        return GameRoomListResult(
            rooms=rooms,
            current_membership=(
                CurrentLobbyMembership(
                    room_public_id=current_room.room_public_id,
                    name=current_room.name,
                    game_type=current_room.game_type,
                    status=current_room.status,
                    max_players=current_room.max_players,
                    member_count=current_room.member_count,
                    is_owner=current_room.is_current_user_owner,
                    lobby_websocket_path=build_lobby_websocket_path(current_room.room_public_id),
                )
                if current_room is not None
                else None
            ),
        )
