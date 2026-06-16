from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GameSessionCredential:
    game_session_token: str
    expires_at: datetime
