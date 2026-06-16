import asyncio
from collections.abc import Callable
from uuid import UUID

from app.be.services.lobby.records import GraceLeaveCallback, LobbyDisconnect


ActiveRoomConnectionChecker = Callable[..., bool]


def schedule_grace_leave_task(
    *,
    disconnect: LobbyDisconnect,
    leave_after_grace: GraceLeaveCallback,
    grace_seconds: float,
    has_active_room_connection: ActiveRoomConnectionChecker,
    pending_grace_leaves: dict[tuple[UUID, UUID], asyncio.Task],
) -> None:
    """grace time 안에 재연결하지 않으면 room 퇴장 콜백을 실행하는 task를 등록합니다."""
    key = grace_leave_key(
        room_public_id=disconnect.room_public_id,
        user_id=disconnect.user.id,
    )
    cancel_pending_grace_leave(
        room_public_id=disconnect.room_public_id,
        user_id=disconnect.user.id,
        pending_grace_leaves=pending_grace_leaves,
    )

    async def run_grace_leave() -> None:
        try:
            await asyncio.sleep(grace_seconds)
            if has_active_room_connection(
                room_public_id=disconnect.room_public_id,
                user_id=disconnect.user.id,
            ):
                return
            await leave_after_grace(disconnect)
        except asyncio.CancelledError:
            return
        finally:
            pending_grace_leaves.pop(key, None)

    pending_grace_leaves[key] = asyncio.create_task(run_grace_leave())


def cancel_pending_grace_leave(
    *,
    room_public_id: UUID,
    user_id: UUID,
    pending_grace_leaves: dict[tuple[UUID, UUID], asyncio.Task],
) -> None:
    """room/user 조합의 pending grace leave task가 있으면 취소합니다."""
    key = grace_leave_key(room_public_id=room_public_id, user_id=user_id)
    pending = pending_grace_leaves.pop(key, None)
    if pending is not None:
        pending.cancel()


def grace_leave_key(*, room_public_id: UUID, user_id: UUID) -> tuple[UUID, UUID]:
    """grace leave task registry에서 사용하는 room/user key를 반환합니다."""
    return room_public_id, user_id
