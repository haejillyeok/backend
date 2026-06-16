from typing import Any
from uuid import UUID

from app.be.services.match.connection_manager import MatchMessage
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


WORD_REJECTION_REASONS = {
    "word_already_used",
    "word_not_in_dictionary",
    "word_start_char_mismatch",
}


def parse_phase_id(value: Any) -> UUID:
    """client payload의 phase_id 문자열을 UUID로 검증합니다."""
    if not isinstance(value, str):
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "phase_id_required"},
        )
    try:
        return UUID(value)
    except ValueError as exc:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "phase_id_invalid"},
        ) from exc


def parse_target_seat_number(value: Any) -> int:
    """투표 대상 공개 순서 번호를 검증합니다."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "target_seat_number_invalid"},
        )
    return value


def extract_next_turn_phase_id(message: MatchMessage) -> UUID | None:
    """진행 event payload에서 다음 턴 phase_id를 추출합니다."""
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    next_turn = payload.get("next_turn")
    if not isinstance(next_turn, dict):
        return None
    phase_id = next_turn.get("phase_id")
    if isinstance(phase_id, UUID):
        return phase_id
    if isinstance(phase_id, str):
        try:
            return UUID(phase_id)
        except ValueError:
            return None
    return None


def word_rejection_from_exception(exc: AppException) -> tuple[str, dict[str, Any]] | None:
    """게임 규칙 위반 AppException을 단어 제출 거절 event 입력으로 변환합니다."""
    if exc.code != ErrorCode.VALIDATION_ERROR or not isinstance(exc.details, dict):
        return None
    reason = exc.details.get("reason")
    if not isinstance(reason, str) or reason not in WORD_REJECTION_REASONS:
        return None
    return reason, {key: value for key, value in exc.details.items() if key != "reason"}


def is_turn_deadline_exception(exc: AppException) -> bool:
    """deadline 이후 제출 예외인지 확인해 timeout 확정 경로로 보낼지 판단합니다."""
    return (
        exc.code == ErrorCode.VALIDATION_ERROR
        and isinstance(exc.details, dict)
        and exc.details.get("reason") == "turn_deadline_exceeded"
    )


def is_vote_deadline_exception(exc: AppException) -> bool:
    """deadline 이후 투표 제출 예외인지 확인해 투표 timeout 확정 경로로 보낼지 판단합니다."""
    return (
        exc.code == ErrorCode.VALIDATION_ERROR
        and isinstance(exc.details, dict)
        and exc.details.get("reason") == "vote_deadline_exceeded"
    )
