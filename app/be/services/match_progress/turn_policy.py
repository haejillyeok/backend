from datetime import datetime
from uuid import UUID

from app.be.models.game import SessionParticipant, SessionPhase, WordTurn
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


class MatchProgressTurnPolicy:
    """현재 턴 검증과 참가자 순서 계산 규칙을 담당합니다."""

    def validate_active_turn(
        self,
        *,
        phase: SessionPhase,
        turn: WordTurn,
        participant_id: UUID,
        now: datetime,
    ) -> None:
        """phase와 turn이 현재 참가자의 활성 턴인지 확인합니다."""
        if phase.finished_at is not None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "phase_already_finished"},
            )
        if phase.deadline_at is not None and now > phase.deadline_at:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "turn_deadline_exceeded"},
            )
        if turn.participant_id != participant_id:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "not_turn_actor"},
            )

    def next_participant(
        self,
        participants: list[SessionParticipant],
        current_participant: SessionParticipant,
    ) -> SessionParticipant:
        """좌석 번호 기준 다음 참가자를 계산합니다."""
        if not participants:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "participants_missing"},
            )
        later_participant = next(
            (
                participant
                for participant in participants
                if participant.seat_number > current_participant.seat_number
            ),
            None,
        )
        return later_participant or participants[0]

    def normalize_word(self, word: str) -> str:
        """제출 단어의 앞뒤 공백을 제거하고 빈 단어를 거부합니다."""
        normalized_word = word.strip()
        if not normalized_word:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "word_empty"},
            )
        return normalized_word

    def word_rejection_score_delta(self, reason: str) -> int:
        """거절 사유별 단어 제출 페널티를 반환합니다."""
        if reason == "word_start_char_mismatch":
            return -5
        if reason == "word_not_in_dictionary":
            return -5
        if reason == "word_already_used":
            return -1
        return 0
