from app.be.services.match.connection_manager import MatchMessage
from app.be.services.realtime import parse_realtime_message


def parse_match_message(raw_message: str) -> MatchMessage:
    """WebSocket text frame을 match JSON envelope로 파싱하고 검증합니다."""
    return parse_realtime_message(raw_message)
