HANGUL_BASE = 0xAC00
HANGUL_END = 0xD7A3
JUNGSEONG_COUNT = 21
JONGSEONG_COUNT = 28
CHOSEONG = (
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
JUNGSEONG = (
    "ㅏ",
    "ㅐ",
    "ㅑ",
    "ㅒ",
    "ㅓ",
    "ㅔ",
    "ㅕ",
    "ㅖ",
    "ㅗ",
    "ㅘ",
    "ㅙ",
    "ㅚ",
    "ㅛ",
    "ㅜ",
    "ㅝ",
    "ㅞ",
    "ㅟ",
    "ㅠ",
    "ㅡ",
    "ㅢ",
    "ㅣ",
)
DUEUM_TO_IEUNG_VOWELS = {"ㅑ", "ㅒ", "ㅕ", "ㅖ", "ㅛ", "ㅠ", "ㅣ"}


def allowed_start_chars_with_dueum(required_start_char: str) -> set[str]:
    """끝말잇기 시작 글자에 두음법칙으로 허용되는 글자를 함께 반환합니다."""
    allowed = {required_start_char}
    decomposed = _decompose_hangul_syllable(required_start_char)
    if decomposed is None:
        return allowed

    choseong, jungseong, jongseong_index = decomposed
    if choseong == "ㄴ" and jungseong in DUEUM_TO_IEUNG_VOWELS:
        allowed.add(_compose_hangul_syllable("ㅇ", jungseong, jongseong_index))
    if choseong == "ㄹ":
        replacement = "ㅇ" if jungseong in DUEUM_TO_IEUNG_VOWELS else "ㄴ"
        allowed.add(_compose_hangul_syllable(replacement, jungseong, jongseong_index))
    return allowed


def _decompose_hangul_syllable(char: str) -> tuple[str, str, int] | None:
    """완성형 한글 한 글자를 초성, 중성, 종성 index로 분해합니다."""
    if len(char) != 1:
        return None
    code = ord(char)
    if not HANGUL_BASE <= code <= HANGUL_END:
        return None
    offset = code - HANGUL_BASE
    choseong_index = offset // (JUNGSEONG_COUNT * JONGSEONG_COUNT)
    jungseong_index = (offset % (JUNGSEONG_COUNT * JONGSEONG_COUNT)) // JONGSEONG_COUNT
    jongseong_index = offset % JONGSEONG_COUNT
    return CHOSEONG[choseong_index], JUNGSEONG[jungseong_index], jongseong_index


def _compose_hangul_syllable(choseong: str, jungseong: str, jongseong_index: int) -> str:
    """초성, 중성, 종성 index를 완성형 한글 한 글자로 합성합니다."""
    choseong_index = CHOSEONG.index(choseong)
    jungseong_index = JUNGSEONG.index(jungseong)
    code = (
        HANGUL_BASE
        + (choseong_index * JUNGSEONG_COUNT + jungseong_index) * JONGSEONG_COUNT
        + jongseong_index
    )
    return chr(code)
