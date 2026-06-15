from pydantic import Field

from app.be.schemas.base import SchemaModel
from app.be.schemas.game_enum import GameType


class GameRoomRuleConfigRequest(SchemaModel):
    max_rounds: int = Field(
        ge=1,
        le=20,
        description="한 게임 세션에서 진행할 끝말잇기 판 수입니다.",
        examples=[8],
    )
    turn_time_seconds: int = Field(
        ge=3,
        le=60,
        description="각 턴의 기본 입력 제한 시간입니다.",
        examples=[10],
    )


class CreateGameRoomRequest(SchemaModel):
    name: str = Field(
        min_length=1,
        max_length=40,
        description="로비 목록과 객실 화면에 표시할 객실 이름입니다.",
        examples=["첫 객실"],
    )
    game_type: GameType = Field(
        description="객실에서 시작할 게임 종류입니다.",
        examples=["word_chain"],
    )
    max_players: int = Field(
        ge=1,
        description="AI 참가자를 제외한 실제 유저 최대 참여 인원입니다.",
        examples=[4],
    )


class UpdateGameRoomRequest(SchemaModel):
    name: str = Field(
        min_length=1,
        max_length=40,
        description="로비 목록과 객실 화면에 표시할 객실 이름입니다.",
        examples=["수정된 객실"],
    )
    max_players: int = Field(
        ge=1,
        description="AI 참가자를 제외한 실제 유저 최대 참여 인원입니다.",
        examples=[5],
    )
    rule_config: GameRoomRuleConfigRequest = Field(
        description="게임 시작 시 세션에 snapshot으로 고정할 객실 룰 설정입니다.",
        examples=[{"max_rounds": 8, "turn_time_seconds": 10}],
    )
