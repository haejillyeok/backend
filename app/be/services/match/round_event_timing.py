from datetime import datetime
from typing import Any

from app.be.services.match.timers import _parse_optional_datetime


MatchMessage = dict[str, Any]


def seconds_until_round_started(message: MatchMessage, *, now: datetime) -> float:
    """`match.round.started` 이벤트를 실제 라운드 시작 시각까지 지연할 초를 계산합니다."""
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return 0.0
    started_at = _parse_optional_datetime(payload.get("started_at"))
    if started_at is None:
        return 0.0
    return max(0.0, (started_at - now).total_seconds())
