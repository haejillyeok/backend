from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.be.services.match.connection_manager import MatchMessage
from app.be.services.match.snapshots import MatchSnapshotResult


@dataclass(frozen=True)
class MatchTurnTimer:
    phase_id: UUID
    deadline_at: datetime


@dataclass(frozen=True)
class MatchVotingTimer:
    deadline_at: datetime


MatchTimer = MatchTurnTimer | MatchVotingTimer


def current_turn_timer_from_snapshot(snapshot: MatchSnapshotResult) -> MatchTurnTimer | None:
    """match snapshot의 현재 턴 deadline을 WebSocket receive 대기 기준으로 변환합니다."""
    if snapshot.current_turn is None or snapshot.current_turn.deadline_at is None:
        return None
    return MatchTurnTimer(
        phase_id=snapshot.current_turn.phase_id,
        deadline_at=snapshot.current_turn.deadline_at,
    )


def current_match_timer_from_snapshot(snapshot: MatchSnapshotResult) -> MatchTimer | None:
    """snapshot의 현재 진행 상태를 WebSocket receive 대기 timer로 변환합니다."""
    turn_timer = current_turn_timer_from_snapshot(snapshot)
    if turn_timer is not None:
        return turn_timer
    if snapshot.voting_deadline_at is not None:
        return MatchVotingTimer(deadline_at=snapshot.voting_deadline_at)
    return None


def seconds_until_match_wait_timeout(
    timer: MatchTimer | None,
    *,
    now: datetime,
    heartbeat_seconds: int = 45,
) -> float:
    """heartbeat와 현재 진행 deadline 중 더 이른 시점까지 기다릴 초를 계산합니다."""
    if timer is None:
        return float(heartbeat_seconds)
    seconds_until_deadline = (timer.deadline_at - now).total_seconds()
    return max(0.0, min(float(heartbeat_seconds), seconds_until_deadline))


def next_match_timer_from_message(message: MatchMessage) -> MatchTimer | None:
    """진행 event payload에서 다음 턴 또는 투표 deadline timer를 추출합니다."""
    next_turn_timer = next_turn_timer_from_message(message)
    if next_turn_timer is not None:
        return next_turn_timer
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    voting_deadline_at = _parse_optional_datetime(payload.get("voting_deadline_at"))
    if voting_deadline_at is None:
        return None
    return MatchVotingTimer(deadline_at=voting_deadline_at)


def next_turn_timer_from_message(message: MatchMessage) -> MatchTurnTimer | None:
    """진행 event의 `next_turn` payload를 다음 timeout timer로 변환합니다."""
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    next_turn = payload.get("next_turn")
    if not isinstance(next_turn, dict):
        return None

    phase_id = _parse_optional_uuid(next_turn.get("phase_id"))
    deadline_at = _parse_optional_datetime(next_turn.get("deadline_at"))
    if phase_id is None or deadline_at is None:
        return None
    return MatchTurnTimer(phase_id=phase_id, deadline_at=deadline_at)


def _parse_optional_uuid(value: Any) -> UUID | None:
    """UUID 또는 UUID 문자열을 선택적으로 파싱합니다."""
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _parse_optional_datetime(value: Any) -> datetime | None:
    """datetime 또는 ISO 문자열을 선택적으로 파싱합니다."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
