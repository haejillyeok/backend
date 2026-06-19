from uuid import UUID

from app.be.services.game.errors import GameRoomEntryForbiddenError, GameRoomNotFoundError
from app.be.services.game.records import (
    RoomLobbyConnectionResult,
    RoomLobbyMemberSnapshot,
    RoomLobbySnapshotResult,
)


class GameRoomLobbyUseCaseMixin:
    async def authorize_room_lobby_connection(
        self,
        *,
        room_public_id: UUID,
        user_id: UUID,
    ) -> RoomLobbyConnectionResult:
        """room 로비 WebSocket 연결 전에 권한을 확인하고 초기 room snapshot을 반환합니다."""
        async with self.repository_scope():
            return await self._authorize_room_lobby_connection(
                room_public_id=room_public_id,
                user_id=user_id,
            )

    async def _authorize_room_lobby_connection(
        self,
        *,
        room_public_id: UUID,
        user_id: UUID,
    ) -> RoomLobbyConnectionResult:
        """로비 WebSocket handshake용 room 권한과 snapshot을 조회합니다."""
        room = await self.repository.get_room_by_public_id(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        member = await self.repository.get_active_room_member(
            room_id=room.id,
            user_id=user_id,
        )
        if member is None:
            raise GameRoomEntryForbiddenError
        members = await self.repository.list_active_room_members(room.id)
        owner = next((member for member in members if member.user_id == room.owner_user_id), None)
        return RoomLobbyConnectionResult(
            room_public_id=room.public_id,
            snapshot=RoomLobbySnapshotResult(
                room_public_id=room.public_id,
                name=room.name,
                game_type=room.game_type,
                status=room.status,
                max_players=room.max_players,
                member_count=len(members),
                rule_config=room.rule_config,
                owner_user_public_id=owner.user_public_id if owner else None,
                members=[
                    RoomLobbyMemberSnapshot(
                        user_public_id=member.user_public_id,
                        nickname=member.nickname,
                        is_owner=member.user_id == room.owner_user_id,
                        joined_at=member.joined_at,
                    )
                    for member in members
                    if member.user_public_id is not None
                ],
            ),
        )
