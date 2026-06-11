import logging

import httpx

from app.agent.prompts import get_prompt
from app.agent.schemas.request.answer import GameType
from app.agent.schemas.word import WordCandidate


logger = logging.getLogger(__name__)


class VllmService:
    """검증된 후보 안에서만 vLLM 선택 결과를 허용합니다."""

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

    async def refine_choice(
        self,
        game_type: GameType,
        candidates: list[WordCandidate],
        fallback: WordCandidate,
    ) -> WordCandidate:
        """vLLM 결과가 후보 목록에 있을 때만 채택하고 나머지는 규칙 결과로 대체합니다."""
        if not self._enabled or not candidates:
            return fallback

        shortlist = candidates[:10]
        candidate_by_word = {candidate.word: candidate for candidate in shortlist}
        prompt = get_prompt(game_type).format(candidates=", ".join(candidate_by_word))
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json={
                        "model": self._model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "max_tokens": 16,
                    },
                )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            normalized = content.strip("\"'` \n")
            return candidate_by_word.get(normalized, fallback)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            logger.warning("vLLM refinement failed; using rule-based fallback")
            return fallback
