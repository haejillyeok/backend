from typing import Any

from app.be.services.match_progress.records import MatchTurnEventPayload


def serialize_next_turn(next_turn: MatchTurnEventPayload) -> dict[str, Any]:
    """다음 턴 record를 `match.turn.resolved` payload의 공통 객체로 변환합니다."""
    return {
        "phase_id": next_turn.phase_id,
        "round_number": next_turn.round_number,
        "turn_number": next_turn.turn_number,
        "actor_seat_number": next_turn.actor_seat_number,
        "started_at": next_turn.started_at,
        "deadline_at": next_turn.deadline_at,
        "required_start_char": next_turn.required_start_char,
    }


def submitted_word_from_ai_failure_details(details: dict[str, Any]) -> str | None:
    """AI 답변 검증 실패 details에서 유저에게 공개할 제출 단어를 꺼냅니다."""
    agent_answer = details.get("agent_answer")
    if isinstance(agent_answer, str) and agent_answer:
        return agent_answer
    return None


def public_ai_failure_details(details: dict[str, Any]) -> dict[str, Any]:
    """Socket client가 내부 구현을 알 수 없도록 AI 전용 details key를 제거합니다."""
    hidden_keys = {"agent_answer", "agent_reason", "error", "status_code"}
    return {key: value for key, value in details.items() if key not in hidden_keys}


def public_ai_failure_reason(reason: str) -> str:
    """도둑잡기 컨셉을 위해 내부 AI/Agent 실패 사유를 공개용 사유로 치환합니다."""
    if reason in {"agent_error", "agent_timeout", "no_candidate"}:
        return "answer_unavailable"
    return reason
