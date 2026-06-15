from enum import StrEnum


class GameType(StrEnum):
    WORD_CHAIN = "word_chain"
    CHOSUNG = "chosung"
    CONTAINS = "contains"


class RoomStatus(StrEnum):
    WAITING = "waiting"
    STARTING = "starting"
    PLAYING = "playing"
    CLOSED = "closed"


class GameSessionStatus(StrEnum):
    STARTING = "starting"
    PLAYING = "playing"
    VOTING = "voting"
    RESULT = "result"
    ABORTED = "aborted"


class ParticipantType(StrEnum):
    USER = "user"
    AI = "ai"
