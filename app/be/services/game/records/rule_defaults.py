from datetime import timedelta

from app.be.schemas.game_enum import GameSessionStatus, RoomStatus


AI_DISPLAY_NAME = "수상한 손님"
GAME_SESSION_TOKEN_TTL = timedelta(hours=3)
STARTING_STATUS = GameSessionStatus.STARTING.value
WAITING_ROOM_STATUS = RoomStatus.WAITING.value
SOLO_ABORTABLE_ROOM_STATUSES = (RoomStatus.STARTING.value, RoomStatus.PLAYING.value)
DEFAULT_ROOM_RULE_CONFIG = {"max_rounds": 8, "turn_time_seconds": 10}
INITIAL_TURN_START_DELAY_SECONDS = 5


def default_room_rule_config() -> dict[str, int]:
    """새 room과 기존 설정 누락 room에 적용할 단어 게임 기본 룰을 반환합니다."""
    return dict(DEFAULT_ROOM_RULE_CONFIG)
