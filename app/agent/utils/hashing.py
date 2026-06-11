import hashlib
import json
import uuid
from typing import Any


POINT_NAMESPACE = uuid.UUID("3d268c98-0ad8-4c61-9d46-faf239b6f730")


def point_id_for_word(word_norm: str) -> str:
    """정규화 단어로부터 결정적 Qdrant point UUID를 생성합니다."""
    return str(uuid.uuid5(POINT_NAMESPACE, word_norm))


def stable_hash(value: Any) -> str:
    """구조화된 값을 정렬 직렬화해 안정적인 SHA-256 해시를 반환합니다."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
