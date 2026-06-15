import logging

import httpx

from app.agent.prompts import (
    get_chosung_fallback_prompt,
    get_contains_fallback_prompt,
    get_word_chain_fallback_prompt,
)
from app.agent.schemas.request.answer import GameType
from app.agent.utils.korean import (
    HANGUL_BASE,
    HANGUL_END,
    extract_chosung,
    normalize_word,
)


logger = logging.getLogger(__name__)


class VllmService:
    """Qdrant 후보가 없을 때 게임 규칙으로 검증 가능한 단어를 생성합니다."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        *,
        enabled: bool,
        timeout_seconds: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._enabled = enabled
        self._timeout_seconds = timeout_seconds

    async def generate_fallback(
        self,
        game_type: GameType,
        condition: str,
        used_words: set[str],
    ) -> str | None:
        """게임별 fallback을 한 번 호출하고 형식과 중복 조건을 검증합니다."""
        if not self._enabled:
            return None

        prompt = self._build_prompt(game_type, condition, used_words)
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json={
                        "model": self._model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.8,
                        "max_tokens": 16,
                    },
                )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            generated_word = normalize_word(content.strip("\"'` \n"))
            if self._is_valid_generated_word(
                generated_word,
                game_type=game_type,
                condition=condition,
                used_words=used_words,
            ):
                return generated_word
            logger.warning(
                "vLLM fallback returned an invalid word",
                extra={"condition": condition},
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            logger.warning("vLLM fallback generation failed")
        return None

    @staticmethod
    def _build_prompt(
        game_type: GameType,
        condition: str,
        used_words: set[str],
    ) -> str:
        prompt_values = {"used_words": ", ".join(sorted(used_words)) or "없음"}
        if game_type == GameType.WORD_CHAIN:
            return get_word_chain_fallback_prompt().format(
                start_char=condition,
                **prompt_values,
            )
        if game_type == GameType.CHOSUNG:
            return get_chosung_fallback_prompt().format(
                chosung=condition,
                **prompt_values,
            )
        return get_contains_fallback_prompt().format(
            contains_word=condition,
            **prompt_values,
        )

    @classmethod
    def _is_valid_generated_word(
        cls,
        word: str,
        *,
        game_type: GameType,
        condition: str,
        used_words: set[str],
    ) -> bool:
        if not cls._is_common_valid_word(word, used_words=used_words):
            return False
        if game_type == GameType.WORD_CHAIN:
            return word.startswith(condition)
        if game_type == GameType.CHOSUNG:
            return extract_chosung(word) == condition
        return condition in word

    @staticmethod
    def _is_common_valid_word(
        word: str,
        *,
        used_words: set[str],
    ) -> bool:
        return (
            2 <= len(word) <= 4
            and word not in used_words
            and all(HANGUL_BASE <= ord(char) <= HANGUL_END for char in word)
        )
