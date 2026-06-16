from dataclasses import dataclass
from datetime import datetime

from app.be.models.game import SessionPhase, WordTurn
from app.be.services.match_progress.records import MatchTurnEventPayload


@dataclass(frozen=True)
class RoundTransitionDraft:
    """턴 종료 후 다음 phase/turn 전환에 필요한 순수 계산 결과를 담습니다."""

    phase: SessionPhase
    turn: WordTurn | None
    payload: dict[str, object]
    next_turn: MatchTurnEventPayload | None
    next_status: str | None
    voting_deadline_at: datetime | None
