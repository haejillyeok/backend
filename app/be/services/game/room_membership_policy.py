from uuid import UUID

from app.be.schemas.game_enum import ParticipantType
from app.be.services.game.records import GameSessionStartResult


class RoomMembershipPolicy:
    """로비 이동 시 기존 room membership 정리 가능 여부를 판단합니다."""

    def is_solo_user_session(self, session: GameSessionStartResult, user_id: UUID) -> bool:
        """AI 참가자를 제외했을 때 현재 유저만 남은 세션인지 확인합니다."""
        user_participants = [
            participant
            for participant in session.participants
            if participant.participant_type == ParticipantType.USER.value
        ]
        return len(user_participants) == 1 and user_participants[0].user_id == user_id
