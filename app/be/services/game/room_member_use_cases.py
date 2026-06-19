from datetime import datetime
from uuid import UUID

from app.be.services.auth import CurrentUser
from app.be.services.game.errors import (
    GameRoomEntryForbiddenError,
    GameRoomNotFoundError,
    GameRoomNotJoinableError,
)
from app.be.services.game.records import (
    RoomJoinResult,
    RoomLeaveResult,
    WAITING_ROOM_STATUS,
)


class GameRoomMemberUseCaseMixin:
    async def quick_join_room(self, *, user: CurrentUser) -> RoomJoinResult:
        """빠른입장용으로 참여 가능한 대기 room을 고르거나 새 room을 만든 뒤 참여시킵니다.

        대상 room 선택과 기존 로비 membership 정리는 유저 단위 advisory lock 안에서 처리해 한 유저가
        여러 대기 room에 active member로 남는 상황을 피합니다.
        """
        async with self.repository_scope():
            await self.repository.lock_waiting_room_membership_for_user(user_id=user.id)
            room = await self.repository.get_oldest_joinable_waiting_room_for_update(
                user_id=user.id,
            )
            created_room = room is None
            if room is None:
                await self._leave_existing_rooms_for_lobby_move(user=user)
                room = await self.repository.create_room(
                    owner_user_id=user.id,
                    name=f"{user.nickname}의 객실",
                    game_type="word_chain",
                    status=WAITING_ROOM_STATUS,
                    max_players=4,
                )
            else:
                await self._leave_existing_rooms_for_lobby_move(
                    user=user,
                    excluded_room_public_id=room.public_id,
                )
            member = await self.repository.create_room_member(
                room_id=room.id,
                user_id=user.id,
                nickname=user.nickname,
            )
            await self.repository.commit()
            return RoomJoinResult(
                room_public_id=room.public_id,
                user_public_id=user.public_id,
                nickname=member.nickname,
                joined_at=member.joined_at,
                already_member=False,
                created_room=created_room,
            )

    async def join_room(self, *, room_public_id: UUID, user: CurrentUser) -> RoomJoinResult:
        """로그인 유저를 대기 중인 room의 활성 멤버로 참여시킵니다.

        이미 참여 중인 유저의 반복 요청은 새 row를 만들지 않고 기존 참여 정보를 반환합니다.
        room 상태와 정원 판단은 room row lock 안에서 수행해 중복 참여와 초과 참여를 줄입니다.
        """
        async with self.repository_scope():
            return await self._join_room(room_public_id=room_public_id, user=user)

    async def _join_room(self, *, room_public_id: UUID, user: CurrentUser) -> RoomJoinResult:
        """room 입장 transaction 안에서 멤버십 검증과 생성을 실행합니다."""
        await self.repository.lock_waiting_room_membership_for_user(user_id=user.id)
        room = await self.repository.get_room_by_public_id_for_update(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        if room.status != WAITING_ROOM_STATUS:
            raise GameRoomNotJoinableError

        existing_member = await self.repository.get_active_room_member(
            room_id=room.id,
            user_id=user.id,
        )
        if existing_member is not None:
            return RoomJoinResult(
                room_public_id=room.public_id,
                user_public_id=user.public_id,
                nickname=existing_member.nickname,
                joined_at=existing_member.joined_at,
                already_member=True,
            )

        members = await self.repository.list_active_room_members(room.id)
        if len(members) >= room.max_players:
            raise GameRoomNotJoinableError

        await self._leave_existing_rooms_for_lobby_move(
            user=user,
            excluded_room_public_id=room.public_id,
        )
        member = await self.repository.create_room_member(
            room_id=room.id,
            user_id=user.id,
            nickname=user.nickname,
        )
        await self.repository.commit()
        return RoomJoinResult(
            room_public_id=room.public_id,
            user_public_id=user.public_id,
            nickname=member.nickname,
            joined_at=member.joined_at,
            already_member=False,
        )

    async def leave_room(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        left_at: datetime,
    ) -> RoomLeaveResult:
        """현재 유저를 대기 room에서 퇴장시키고 방장 승계 또는 room 폐쇄를 처리합니다."""
        async with self.repository_scope():
            result = await self._leave_waiting_room(
                room_public_id=room_public_id,
                user=user,
                left_at=left_at,
                ignore_inactive_member=False,
                commit=True,
            )
        if result is None:
            raise GameRoomEntryForbiddenError
        return result

    async def leave_room_after_disconnect_grace(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        left_at: datetime,
    ) -> RoomLeaveResult | None:
        """WebSocket grace timeout 이후에도 복귀하지 않은 유저를 room에서 퇴장 처리합니다.

        이미 다른 흐름에서 퇴장됐거나 room이 더 이상 대기 로비가 아니면 DB를 다시 변경하지 않고
        None을 반환합니다.
        """
        async with self.repository_scope():
            return await self._leave_waiting_room(
                room_public_id=room_public_id,
                user=user,
                left_at=left_at,
                ignore_inactive_member=True,
                commit=True,
            )
