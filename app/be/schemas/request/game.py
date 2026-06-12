from pydantic import Field

from app.be.schemas.base import SchemaModel


class CreateGameRoomRequest(SchemaModel):
    name: str = Field(
        min_length=1,
        max_length=40,
        description="로비 목록과 객실 화면에 표시할 객실 이름입니다.",
        examples=["첫 객실"],
    )
    game_type: str = Field(
        min_length=1,
        max_length=40,
        description="객실에서 시작할 게임 종류입니다.",
        examples=["shiritori"],
    )
    max_players: int = Field(
        ge=1,
        description="AI 참가자를 제외한 실제 유저 최대 참여 인원입니다.",
        examples=[4],
    )
