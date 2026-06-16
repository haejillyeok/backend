from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


class GameRoomNotFoundError(AppException):
    """요청한 room public_id가 존재하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_NOT_FOUND)


class GameRoomStartForbiddenError(AppException):
    """방장 또는 허용된 멤버가 아닌 유저가 게임 시작을 요청할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_START_FORBIDDEN)


class GameRoomNotStartableError(AppException):
    """room 상태나 멤버 조건이 게임 시작을 허용하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_NOT_STARTABLE)


class GameRoomNotJoinableError(AppException):
    """room 상태나 정원 조건이 참여를 허용하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_NOT_JOINABLE)


class GameRoomUpdateForbiddenError(AppException):
    """방장이 아닌 유저가 room 설정 변경을 요청할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_UPDATE_FORBIDDEN)


class GameRoomNotUpdateableError(AppException):
    """room 상태가 설정 변경을 허용하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_NOT_UPDATEABLE)


class GameRoomEntryForbiddenError(AppException):
    """room 활성 멤버가 아닌 유저가 room 로비에 진입하려 할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_ENTRY_FORBIDDEN)


class GameSessionEntryForbiddenError(AppException):
    """게임 세션 참가자로 고정되지 않은 유저가 진입하려 할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN)
