from uuid import UUID

from app.be.services.auth import CurrentUser
from app.be.services.game.errors import (
    GameRoomNotFoundError,
    GameRoomNotUpdateableError,
    GameRoomUpdateForbiddenError,
)
from app.be.services.game.records import (
    RoomCreateResult,
    RoomUpdateResult,
    WAITING_ROOM_STATUS,
)
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


class GameRoomSettingsUseCaseMixin:
    async def create_room(
        self,
        *,
        name: str,
        game_type: str,
        max_players: int,
        owner: CurrentUser,
    ) -> RoomCreateResult:
        """대기 상태 객실을 만들고 방장을 첫 활성 멤버로 등록합니다.

        room 생성과 방장 멤버십 생성은 같은 transaction에서 확정합니다. 이후 로비 WebSocket은 이
        `room_members` 행을 기준으로 연결 권한을 확인합니다.
        """
        async with self.repository_scope():
            return await self._create_room(
                name=name,
                game_type=game_type,
                max_players=max_players,
                owner=owner,
            )

    async def _create_room(
        self,
        *,
        name: str,
        game_type: str,
        max_players: int,
        owner: CurrentUser,
    ) -> RoomCreateResult:
        """room 생성 transaction 안에서 DB 변경을 순서대로 실행합니다."""
        await self.repository.lock_waiting_room_membership_for_user(user_id=owner.id)
        await self._leave_existing_rooms_for_lobby_move(user=owner)
        room = await self.repository.create_room(
            owner_user_id=owner.id,
            name=name,
            game_type=game_type,
            status=WAITING_ROOM_STATUS,
            max_players=max_players,
        )
        await self.repository.create_room_member(
            room_id=room.id,
            user_id=owner.id,
            nickname=owner.nickname,
        )
        await self.repository.commit()
        if room.created_at is None:
            raise AppException(
                code=ErrorCode.HTTP_ERROR,
                details={"reason": "room_created_at_missing"},
            )
        return RoomCreateResult(
            room_public_id=room.public_id,
            name=room.name,
            game_type=room.game_type,
            status=room.status,
            max_players=room.max_players,
            member_count=1,
            created_at=room.created_at,
        )

    async def update_room(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        name: str,
        max_players: int,
        rule_config: dict[str, int],
    ) -> RoomUpdateResult:
        """방장이 대기 중인 객실의 게임 시작 전 설정을 수정합니다.

        room row lock 안에서 방장, 상태, 현재 활성 멤버 수를 검증하고 DB 설정만 확정합니다.
        WebSocket 동기화는 API endpoint가 commit 이후 별도로 수행합니다.
        """
        async with self.repository_scope():
            return await self._update_room(
                room_public_id=room_public_id,
                user=user,
                name=name,
                max_players=max_players,
                rule_config=rule_config,
            )

    async def _update_room(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        name: str,
        max_players: int,
        rule_config: dict[str, int],
    ) -> RoomUpdateResult:
        """room 설정 변경 transaction 안에서 검증과 저장을 실행합니다."""
        room = await self.repository.get_room_by_public_id_for_update(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        if room.owner_user_id != user.id:
            raise GameRoomUpdateForbiddenError
        if room.status != WAITING_ROOM_STATUS:
            raise GameRoomNotUpdateableError
        members = await self.repository.list_active_room_members(room.id)
        if len(members) > max_players:
            raise GameRoomNotUpdateableError
        result = await self.repository.update_room_settings(
            room_id=room.id,
            name=name,
            max_players=max_players,
            rule_config=rule_config,
        )
        await self.repository.commit()
        return result
