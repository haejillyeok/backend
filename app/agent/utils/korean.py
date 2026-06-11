import unicodedata


CHOSUNG = (
    "ㄱ",
    "ㄲ",
    "ㄴ",
    "ㄷ",
    "ㄸ",
    "ㄹ",
    "ㅁ",
    "ㅂ",
    "ㅃ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅉ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
)
HANGUL_BASE = 0xAC00
HANGUL_END = 0xD7A3
JUNGSEONG_COUNT = 21
JONGSEONG_COUNT = 28


def normalize_word(word: str) -> str:
    """단어를 NFC로 정규화하고 모든 공백을 제거합니다."""
    normalized = unicodedata.normalize("NFC", word)
    return "".join(normalized.split())


def split_syllables(word: str) -> list[str]:
    """정규화된 단어를 글자 단위 목록으로 분리합니다."""
    return list(normalize_word(word))


def extract_start_word(word: str) -> str:
    """단어의 첫 글자를 반환하며 빈 단어는 빈 문자열을 반환합니다."""
    syllables = split_syllables(word)
    return syllables[0] if syllables else ""


def extract_end_word(word: str) -> str:
    """단어의 마지막 글자를 반환하며 빈 단어는 빈 문자열을 반환합니다."""
    syllables = split_syllables(word)
    return syllables[-1] if syllables else ""


def extract_chosung(word: str) -> str:
    """한글 음절의 초성을 추출하고 비한글 문자는 그대로 유지합니다."""
    result: list[str] = []
    for char in split_syllables(word):
        code = ord(char)
        if HANGUL_BASE <= code <= HANGUL_END:
            index = (code - HANGUL_BASE) // (JUNGSEONG_COUNT * JONGSEONG_COUNT)
            result.append(CHOSUNG[index])
        else:
            result.append(char)
    return "".join(result)


def build_word_payload(word: str) -> dict:
    """단어 하나를 Qdrant 적재용 payload로 변환합니다."""
    word_norm = normalize_word(word)
    if not word_norm:
        raise ValueError("word must not be blank")
    syllables = split_syllables(word_norm)
    return {
        "word": word_norm,
        "start_word": syllables[0],
        "end_word": syllables[-1],
        "chosung": extract_chosung(word_norm),
        "syllables": syllables,
        "length": len(syllables),
        "used_count": 0,
    }
