from app.agent.schemas.request.answer import GameType


SHIRITORI_PROMPT = """\
다음 검증된 끝말잇기 후보 중 사람 플레이어처럼 자연스러운 단어 하나만 그대로 출력하세요.
후보 밖의 단어를 만들거나 설명을 추가하지 마세요.
후보: {candidates}
"""

CHOSUNG_PROMPT = """\
다음 검증된 초성 게임 후보 중 하나만 그대로 출력하세요.
후보 밖의 단어를 만들거나 설명을 추가하지 마세요.
후보: {candidates}
"""

CONTAINS_PROMPT = """\
다음 검증된 낱말 포함 게임 후보 중 하나만 그대로 출력하세요.
후보 밖의 단어를 만들거나 설명을 추가하지 마세요.
후보: {candidates}
"""

PROMPTS: dict[GameType, str] = {
    GameType.SHIRITORI: SHIRITORI_PROMPT,
    GameType.CHOSUNG: CHOSUNG_PROMPT,
    GameType.CONTAINS: CONTAINS_PROMPT,
}


def get_prompt(game_type: GameType) -> str:
    """게임 종류별 변수 기반 프롬프트를 반환합니다."""
    return PROMPTS[game_type]
