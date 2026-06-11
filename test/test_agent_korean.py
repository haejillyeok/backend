from app.agent.utils.korean import (
    build_word_payload,
    extract_chosung,
    extract_end_word,
    extract_start_word,
    normalize_word,
    split_syllables,
)


def test_extract_chosung() -> None:
    assert extract_chosung("사과") == "ㅅㄱ"
    assert extract_chosung("고구마밭") == "ㄱㄱㅁㅂ"


def test_split_and_edge_syllables() -> None:
    assert split_syllables("사과") == ["사", "과"]
    assert extract_start_word("고구마밭") == "고"
    assert extract_end_word("고구마밭") == "밭"


def test_normalize_and_build_payload() -> None:
    assert normalize_word("  고구마밭 ") == "고구마밭"
    assert build_word_payload("고구마밭") == {
        "word": "고구마밭",
        "start_word": "고",
        "end_word": "밭",
        "chosung": "ㄱㄱㅁㅂ",
        "syllables": ["고", "구", "마", "밭"],
        "length": 4,
        "used_count": 0,
    }
