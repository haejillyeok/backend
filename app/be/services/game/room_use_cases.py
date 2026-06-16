from app.be.services.game.room_listing_use_cases import GameRoomListingUseCaseMixin
from app.be.services.game.room_lobby_use_cases import GameRoomLobbyUseCaseMixin
from app.be.services.game.room_member_use_cases import GameRoomMemberUseCaseMixin
from app.be.services.game.room_settings_use_cases import GameRoomSettingsUseCaseMixin


class GameRoomUseCaseMixin(
    GameRoomListingUseCaseMixin,
    GameRoomSettingsUseCaseMixin,
    GameRoomLobbyUseCaseMixin,
    GameRoomMemberUseCaseMixin,
):
    """room 목록, 설정, 로비 접근, 참여/퇴장 use case mixin을 조합합니다."""
