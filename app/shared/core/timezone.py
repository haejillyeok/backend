from datetime import datetime
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


def kst_now() -> datetime:
    """DB 저장, 만료 비교, 외부 응답에 사용할 KST aware 현재 시각을 반환합니다."""
    return datetime.now(KST)


def to_kst(value: datetime) -> datetime:
    """timezone-aware datetime을 KST로 변환하고, naive 값은 KST로 해석합니다."""
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def to_kst_isoformat(value: datetime) -> str:
    """API/WebSocket payload에 사용할 KST ISO-8601 문자열을 반환합니다."""
    return to_kst(value).isoformat()
