from uuid import UUID

from app.be.schemas.game_enum import ParticipantType
from app.be.services.game.records import GameSessionParticipantRecord, RoomMemberRecord


def build_anonymous_display_name(seat_number: int) -> str:
    """게임 진행 중 참가자 정체를 숨기기 위해 좌석 번호 기반 표시명을 만듭니다."""
    return f"{seat_number}번 손님"


class SessionParticipantPolicy:
    """게임 시작 시 실제 유저와 AI 손님 참가자 snapshot을 생성합니다."""

    def build_participants(
        self,
        *,
        game_session_public_id: UUID,
        members: list[RoomMemberRecord],
    ) -> list[GameSessionParticipantRecord]:
        """활성 room member를 익명 참가자로 고정하고 마지막 좌석에 AI 손님을 추가합니다."""
        participants = [
            GameSessionParticipantRecord(
                participant_id=None,
                game_session_public_id=game_session_public_id,
                user_id=member.user_id,
                participant_type=ParticipantType.USER.value,
                display_name=build_anonymous_display_name(index),
                seat_number=index,
                is_uninvited_guest=False,
                original_nickname=member.nickname,
            )
            for index, member in enumerate(members, start=1)
        ]
        ai_seat_number = len(participants) + 1
        participants.append(
            GameSessionParticipantRecord(
                participant_id=None,
                game_session_public_id=game_session_public_id,
                user_id=None,
                participant_type=ParticipantType.AI.value,
                display_name=build_anonymous_display_name(ai_seat_number),
                seat_number=ai_seat_number,
                is_uninvited_guest=True,
            )
        )
        return participants
