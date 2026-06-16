from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


AI_ANSWER_REJECTION_REASONS = {
    "word_already_used",
    "word_empty",
    "word_not_in_dictionary",
    "word_start_char_mismatch",
}


def is_stale_ai_turn_exception(exc: AppException) -> bool:
    """AI Agent 응답 대기 중 이미 종료된 phase에서 발생한 progress 예외인지 확인합니다."""
    return (
        exc.code == ErrorCode.VALIDATION_ERROR
        and isinstance(exc.details, dict)
        and exc.details.get("reason") == "phase_already_finished"
    )


def is_ai_turn_deadline_exception(exc: AppException) -> bool:
    """AI 답변이 도착했지만 서버 deadline이 지난 경우 timeout 확정 경로로 보낼지 판단합니다."""
    return (
        exc.code == ErrorCode.VALIDATION_ERROR
        and isinstance(exc.details, dict)
        and exc.details.get("reason") == "turn_deadline_exceeded"
    )


def ai_answer_rejection_reason(exc: AppException) -> str | None:
    """AI가 낸 단어가 Backend 단어 규칙을 통과하지 못한 사유를 반환합니다."""
    if exc.code != ErrorCode.VALIDATION_ERROR or not isinstance(exc.details, dict):
        return None
    reason = exc.details.get("reason")
    if isinstance(reason, str) and reason in AI_ANSWER_REJECTION_REASONS:
        return reason
    return None


def ai_answer_rejection_details(
    *,
    reason: str,
    details: object,
) -> dict[str, object]:
    """AI 제출 단어의 검증 실패를 일반 단어 거절 details로 변환합니다."""
    failure_details: dict[str, object] = {
        "validation_reason": reason,
    }
    if isinstance(details, dict):
        failure_details.update({key: value for key, value in details.items() if key != "reason"})
    return failure_details


def ai_no_candidate_details(answer: str | None, reason: str | None) -> dict[str, object]:
    """Agent가 실패 상태와 함께 후보 단어를 돌려준 경우 UI에 공개할 수 있게 보존합니다."""
    failure_details: dict[str, object] = {"agent_reason": reason}
    if answer:
        failure_details["agent_answer"] = answer
    return failure_details
