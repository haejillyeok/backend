from secrets import randbits
from time import time_ns
from uuid import UUID


def generate_uuid_v7() -> UUID:
    """시간 정렬성을 갖는 RFC 9562 UUID v7 값을 생성합니다."""
    timestamp_ms = time_ns() // 1_000_000
    random_a = randbits(12)
    random_b = randbits(62)

    uuid_int = (timestamp_ms & ((1 << 48) - 1)) << 80
    uuid_int |= 0x7 << 76
    uuid_int |= random_a << 64
    uuid_int |= 0b10 << 62
    uuid_int |= random_b

    return UUID(int=uuid_int)
