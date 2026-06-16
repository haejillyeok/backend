from dataclasses import dataclass

from app.be.models.game import SessionPhase, WordTurn


@dataclass(frozen=True)
class NextWordTurnDraft:
    """승인된 단어 제출 뒤 생성할 다음 phase와 turn, event payload 초안입니다."""

    phase: SessionPhase
    turn: WordTurn
    payload: dict[str, object]
    required_start_char: str
