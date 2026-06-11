from app.agent.utils.korean import build_word_payload, normalize_word


class WordService:
    """입력 단어의 정규화, 중복 제거, payload 생성을 담당합니다."""

    def prepare_payloads(
        self,
        words: list[str],
        game_types: list[str],
        *,
        is_valid: bool,
        is_banned: bool,
    ) -> list[dict]:
        """단어 목록을 중복 제거한 Qdrant payload 목록으로 변환합니다."""
        deduplicated: dict[str, str] = {}
        for word in words:
            word_norm = normalize_word(word)
            if word_norm:
                deduplicated.setdefault(word_norm, word)

        payloads = []
        for word in deduplicated.values():
            payload = build_word_payload(word, game_types)
            payload["is_valid"] = is_valid
            payload["is_banned"] = is_banned
            payloads.append(payload)
        return payloads
