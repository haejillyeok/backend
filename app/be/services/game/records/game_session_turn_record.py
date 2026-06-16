from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class GameSessionTurnRecord:
    phase_id: UUID
    round_number: int
    turn_number: int
    actor_seat_number: int
    started_at: datetime
    deadline_at: datetime | None
    required_start_char: str | None
