import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from app.be.models.game import SessionParticipant
from app.be.services.game.records import INITIAL_TURN_START_DELAY_SECONDS
from app.shared.core.timezone import kst_now


@dataclass(frozen=True)
class InitialWordTurnDraft:
    """끝말잇기 세션 시작 직후 첫 턴 row들을 만들기 위한 순수 계산 결과입니다."""

    phase_type: str
    phase_number: int
    round_number: int
    turn_number: int
    condition_payload: dict[str, str | None]
    time_limit_seconds: int
    started_at: datetime
    deadline_at: datetime


class SessionInitialTurnPolicy:
    """게임 세션 시작 시 필요한 첫 턴 정책을 DB 의존 없이 계산합니다."""

    def __init__(self, random_source: random.Random | None = None) -> None:
        self._random = random_source or random.SystemRandom()

    def choose_round_start_participant(
        self,
        participant_rows: Sequence[SessionParticipant],
    ) -> SessionParticipant:
        """라운드 시작 actor를 참가자 확정 이후 무작위로 선택합니다."""
        if not participant_rows:
            raise ValueError("participant_rows must not be empty")
        return self._random.choice(list(participant_rows))

    def build_word_chain_initial_turn(
        self,
        *,
        rule_config: dict[str, int],
        required_start_char: str | None,
    ) -> InitialWordTurnDraft:
        """끝말잇기 첫 턴의 phase/turn 공통 조건과 시간을 계산합니다."""
        started_at = kst_now() + timedelta(seconds=INITIAL_TURN_START_DELAY_SECONDS)
        turn_time_seconds = int(rule_config.get("turn_time_seconds", 10))
        condition_payload = {"required_start_char": required_start_char}
        return InitialWordTurnDraft(
            phase_type="turn",
            phase_number=1,
            round_number=1,
            turn_number=1,
            condition_payload=condition_payload,
            time_limit_seconds=turn_time_seconds,
            started_at=started_at,
            deadline_at=started_at + timedelta(seconds=turn_time_seconds),
        )
