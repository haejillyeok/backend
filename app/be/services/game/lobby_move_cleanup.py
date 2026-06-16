from datetime import datetime
from uuid import UUID

from app.be.services.auth import CurrentUser
from app.be.services.game.records import (
    GameRoomRecord,
    SOLO_ABORTABLE_ROOM_STATUSES,
    WAITING_ROOM_STATUS,
)
from app.shared.core.timezone import kst_now


class GameLobbyMoveCleanupMixin:
    async def _leave_existing_rooms_for_lobby_move(
        self,
        *,
        user: CurrentUser,
        excluded_room_public_id: UUID | None = None,
    ) -> None:
        """새 대기방 생성/입장 전 유저가 남아 있던 다른 room membership을 정리합니다.

        한 유저가 여러 room에 동시에 active member로 남으면 로비 목록에 유령 객실이 누적됩니다.
        대기 room은 REST 퇴장과 같은 규칙으로 정리하고, 이미 시작됐지만 실제 유저가 현재 유저
        한 명뿐인 세션은 다른 유저에게 영향이 없으므로 abort 후 room을 닫습니다. 같은 room 반복
        입장은 기존 membership을 그대로 반환해야 하므로 제외합니다.
        """
        room_public_ids = await self.repository.list_active_room_public_ids_for_user(
            user_id=user.id,
        )
        for room_public_id in room_public_ids:
            if room_public_id == excluded_room_public_id:
                continue
            room = await self.repository.get_room_by_public_id_for_update(room_public_id)
            if room is None:
                continue
            left_at = kst_now()
            if room.status == WAITING_ROOM_STATUS:
                await self._leave_locked_waiting_room(
                    room=room,
                    user=user,
                    left_at=left_at,
                    ignore_inactive_member=True,
                    commit=False,
                )
                continue
            if room.status in SOLO_ABORTABLE_ROOM_STATUSES:
                await self._abort_solo_started_room(room=room, user=user, left_at=left_at)

    async def _abort_solo_started_room(
        self,
        *,
        room: GameRoomRecord,
        user: CurrentUser,
        left_at: datetime,
    ) -> None:
        """실제 유저가 1명뿐인 started room을 새 로비 이동 전 안전하게 닫습니다."""
        active_session = await self._get_active_session_result(room.id)
        if active_session is None or not self.room_membership_policy.is_solo_user_session(
            active_session,
            user.id,
        ):
            return
        leave_result = await self.repository.mark_room_member_left(
            room_id=room.id,
            user_id=user.id,
            left_at=left_at,
        )
        if leave_result is None:
            return
        await self.repository.abort_active_session_for_room(room_id=room.id, ended_at=left_at)
        await self.repository.close_room(room_id=room.id, closed_at=left_at)
