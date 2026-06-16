from app.be.services.game.lobby_move_cleanup import GameLobbyMoveCleanupMixin
from app.be.services.game.waiting_room_leave import GameWaitingRoomLeaveMixin


class GameMembershipUseCaseMixin(
    GameLobbyMoveCleanupMixin,
    GameWaitingRoomLeaveMixin,
):
    """room membership 내부 helper mixin을 기존 import 경로로 조합합니다."""
