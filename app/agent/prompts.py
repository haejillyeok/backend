SHIRITORI_FALLBACK_PROMPT = """\
한국어 끝말잇기에서 사용할 단어 하나를 생성하세요.
반드시 "{start_char}" 글자로 시작하고, 완성형 한글 2글자 이상 4글자 이하의 실제 단어여야 합니다.
다음 사용된 단어는 생성하지 마세요: {used_words}
설명, 문장, 따옴표, 번호, 코드 블록 없이 단어 하나만 출력하세요.
"""


def get_shiritori_fallback_prompt() -> str:
    """Qdrant 후보가 없을 때 사용하는 끝말잇기 생성 프롬프트를 반환합니다."""
    return SHIRITORI_FALLBACK_PROMPT
