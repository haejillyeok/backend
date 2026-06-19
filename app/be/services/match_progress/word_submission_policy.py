from datetime import datetime, timedelta

from app.be.models.game import (
    GameSession,
    SessionParticipant,
    SessionPhase,
    ValidWord,
    WordTurn,
)
from app.be.services.match_progress.word_turn_drafts import NextWordTurnDraft
from app.shared.core.korean import allowed_start_chars_with_dueum
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException
from app.shared.core.identifiers import generate_uuid_v7


class WordSubmissionPolicy:
    """단어 제출 승인 시 다음 턴과 공개 event payload 조립 규칙을 담당합니다."""

    def accepted_score_delta(self) -> int:
        """단어 제출 승인으로 얻는 기본 점수를 반환합니다."""
        return 10

    def ensure_word_starts_with_required_char(
        self,
        *,
        normalized_word: str,
        required_start_char: str | None,
    ) -> None:
        """현재 턴의 시작 글자 조건을 만족하는지 확인합니다."""
        if required_start_char and (
            not normalized_word
            or normalized_word[0] not in allowed_start_chars_with_dueum(required_start_char)
        ):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={
                    "reason": "word_start_char_mismatch",
                    "required_start_char": required_start_char,
                },
            )

    def ensure_word_is_valid(self, valid_word: ValidWord | object | None) -> None:
        """사전에 등록된 활성 단어인지 확인합니다."""
        if valid_word is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "word_not_in_dictionary"},
            )

    def ensure_word_not_used(self, used_word: object | None) -> None:
        """같은 라운드에서 이미 사용된 단어가 아닌지 확인합니다."""
        if used_word is not None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "word_already_used"},
            )

    def build_next_turn(
        self,
        *,
        game_session: GameSession,
        phase: SessionPhase,
        turn: WordTurn,
        next_participant: SessionParticipant,
        normalized_word: str,
        now: datetime,
    ) -> NextWordTurnDraft:
        """제출 단어의 마지막 글자를 조건으로 다음 턴 phase와 turn을 만듭니다."""
        next_required_start_char = normalized_word[-1]
        turn_time_seconds = int(game_session.rule_config.get("turn_time_seconds", 10))
        next_phase = SessionPhase(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_type="turn",
            phase_number=phase.phase_number + 1,
            actor_participant_id=next_participant.id,
            condition_payload={"required_start_char": next_required_start_char},
            time_limit_seconds=turn_time_seconds,
            started_at=now,
            deadline_at=now + timedelta(seconds=turn_time_seconds),
        )
        next_turn = WordTurn(
            id=generate_uuid_v7(),
            phase_id=next_phase.id,
            participant_id=next_participant.id,
            round_number=turn.round_number,
            turn_number=turn.turn_number + 1,
            condition_payload=next_phase.condition_payload,
        )
        return NextWordTurnDraft(
            phase=next_phase,
            turn=next_turn,
            payload={
                "phase_id": str(next_phase.id),
                "round_number": next_turn.round_number,
                "turn_number": next_turn.turn_number,
                "actor_seat_number": next_participant.seat_number,
                "started_at": next_phase.started_at.isoformat(),
                "deadline_at": next_phase.deadline_at.isoformat(),
                "required_start_char": next_required_start_char,
            },
            required_start_char=next_required_start_char,
        )

    def build_accepted_event_payload(
        self,
        *,
        phase: SessionPhase,
        participant: SessionParticipant,
        normalized_word: str,
        score_delta: int,
        next_turn_payload: dict[str, object],
    ) -> dict[str, object]:
        """`word.accepted` event의 공개 payload를 만듭니다."""
        return {
            "phase_id": str(phase.id),
            "participant": {
                "display_name": participant.display_name,
                "seat_number": participant.seat_number,
            },
            "word": normalized_word,
            "normalized_word": normalized_word,
            "score_delta": score_delta,
            "next_turn": next_turn_payload,
        }
