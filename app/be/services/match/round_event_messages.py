from typing import Any


MatchMessage = dict[str, Any]


def round_finished_message_from_turn_resolved(message: MatchMessage) -> MatchMessage | None:
    """턴 timeout event가 라운드 종료를 만들었을 때 공개 `match.round.finished` event로 변환합니다."""
    if message.get("type") != "match.turn.resolved":
        return None
    payload = message.get("payload")
    if not isinstance(payload, dict) or payload.get("result") != "timeout":
        return None
    if not isinstance(payload.get("next_turn"), dict) and payload.get("next_status") is None:
        return None

    round_number = _round_number_from_timeout_payload(payload)
    if round_number is None:
        return None

    round_payload: dict[str, Any] = {
        "event_sequence": payload.get("event_sequence"),
        "phase_id": payload.get("phase_id"),
        "round_number": round_number,
        "result": "timeout",
        "reason": payload.get("reason"),
        "participant": payload.get("participant"),
        "deadline_at": payload.get("deadline_at"),
        "created_at": payload.get("created_at"),
        "server_time": payload.get("server_time") or payload.get("created_at"),
    }
    for key in ("next_turn", "next_status", "voting_deadline_at"):
        if key in payload:
            round_payload[key] = payload[key]
    return {"type": "match.round.finished", "payload": round_payload}


def round_started_message_from_turn_resolved(message: MatchMessage) -> MatchMessage | None:
    """다음 라운드 첫 턴이 생성된 timeout event를 공개 `match.round.started` event로 변환합니다."""
    if message.get("type") != "match.turn.resolved":
        return None
    payload = message.get("payload")
    if not isinstance(payload, dict) or payload.get("result") != "timeout":
        return None
    next_turn = payload.get("next_turn")
    if not isinstance(next_turn, dict):
        return None
    round_number = next_turn.get("round_number")
    if not isinstance(round_number, int) or isinstance(round_number, bool):
        return None
    return {
        "type": "match.round.started",
        "payload": {
            "event_sequence": payload.get("event_sequence"),
            "round_number": round_number,
            "current_turn": next_turn,
            "started_at": next_turn.get("started_at") or payload.get("created_at"),
            "created_at": payload.get("created_at"),
            "server_time": next_turn.get("started_at")
            or payload.get("server_time")
            or payload.get("created_at"),
        },
    }


def _round_number_from_timeout_payload(payload: dict[str, Any]) -> int | None:
    """timeout payload에서 종료된 라운드 번호를 얻거나 다음 라운드 번호로 보수적으로 추론합니다."""
    round_number = payload.get("round_number")
    if isinstance(round_number, int) and not isinstance(round_number, bool):
        return round_number
    next_turn = payload.get("next_turn")
    if not isinstance(next_turn, dict):
        return None
    next_round_number = next_turn.get("round_number")
    if isinstance(next_round_number, int) and not isinstance(next_round_number, bool):
        return max(1, next_round_number - 1)
    return None
