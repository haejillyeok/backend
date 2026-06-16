from datetime import datetime
from uuid import UUID

from app.be.services.auth import CurrentUser
from app.be.services.game.errors import (
    GameRoomEntryForbiddenError,
    GameRoomNotFoundError,
    GameRoomNotJoinableError,
)
from app.be.services.game.records import (
    GameRoomRecord,
    RoomLeaveResult,
    WAITING_ROOM_STATUS,
)


class GameWaitingRoomLeaveMixin:
    async def _leave_waiting_room(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        left_at: datetime,
        ignore_inactive_member: bool,
        commit: bool,
    ) -> RoomLeaveResult | None:
        """대기 room 퇴장 후 남은 멤버 기준으로 방장 승계 또는 room 폐쇄를 결정합니다."""
        room = await self.repository.get_room_by_public_id_for_update(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        if room.status != WAITING_ROOM_STATUS:
            if ignore_inactive_member:
                return None
            raise GameRoomNotJoinableError
        return await self._leave_locked_waiting_room(
            room=room,
            user=user,
            left_at=left_at,
            ignore_inactive_member=ignore_inactive_member,
            commit=commit,
        )

    async def _leave_locked_waiting_room(
        self,
        *,
        room: GameRoomRecord,
        user: CurrentUser,
        left_at: datetime,
        ignore_inactive_member: bool,
        commit: bool,
    ) -> RoomLeaveResult | None:
        """이미 lock을 잡은 대기 room의 퇴장, 방장 승계, 폐쇄를 처리합니다."""
        result = await self.repository.mark_room_member_left(
            room_id=room.id,
            user_id=user.id,
            left_at=left_at,
        )
        if result is None:
            if ignore_inactive_member:
                return None
            raise GameRoomEntryForbiddenError
        remaining_members = await self.repository.list_active_room_members(room.id)
        new_owner = None
        room_closed = False
        if not remaining_members:
            await self.repository.close_room(room_id=room.id, closed_at=left_at)
            room_closed = True
        elif room.owner_user_id == user.id:
            new_owner = remaining_members[0]
            await self.repository.transfer_room_owner(
                room_id=room.id,
                owner_user_id=new_owner.user_id,
            )
        if commit:
            await self.repository.commit()
        return RoomLeaveResult(
            room_public_id=room.public_id,
            user_public_id=user.public_id,
            nickname=result.nickname,
            left_at=result.left_at,
            remaining_member_count=len(remaining_members),
            new_owner_user_public_id=new_owner.user_public_id if new_owner else None,
            new_owner_nickname=new_owner.nickname if new_owner else None,
            room_closed=room_closed,
        )
