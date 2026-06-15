from app.agent.schemas.request.answer import GameType
from app.agent.services.vllm import VllmService


def test_generated_word_common_validation() -> None:
    validator = VllmService._is_valid_generated_word

    assert validator(
        "자전거",
        game_type=GameType.WORD_CHAIN,
        condition="자",
        used_words=set(),
    )
    assert not validator(
        "자동차",
        game_type=GameType.WORD_CHAIN,
        condition="자",
        used_words={"자동차"},
    )
    assert not validator(
        "기차",
        game_type=GameType.WORD_CHAIN,
        condition="자",
        used_words=set(),
    )
    assert not validator(
        "자",
        game_type=GameType.WORD_CHAIN,
        condition="자",
        used_words=set(),
    )
    assert not validator(
        "자전거놀이",
        game_type=GameType.WORD_CHAIN,
        condition="자",
        used_words=set(),
    )
    assert not validator(
        "자전1",
        game_type=GameType.WORD_CHAIN,
        condition="자",
        used_words=set(),
    )


def test_generated_chosung_word_validation() -> None:
    validator = VllmService._is_valid_generated_word

    assert validator(
        "고구마",
        game_type=GameType.CHOSUNG,
        condition="ㄱㄱㅁ",
        used_words=set(),
    )
    assert not validator(
        "고구마",
        game_type=GameType.CHOSUNG,
        condition="ㄱㅁ",
        used_words=set(),
    )


def test_generated_contains_word_validation() -> None:
    validator = VllmService._is_valid_generated_word

    assert validator(
        "고구마",
        game_type=GameType.CONTAINS,
        condition="마",
        used_words=set(),
    )
    assert not validator(
        "고구마",
        game_type=GameType.CONTAINS,
        condition="사",
        used_words=set(),
    )


def test_game_specific_prompt_selection() -> None:
    used_words = {"사과"}

    assert '"자"' in VllmService._build_prompt(GameType.WORD_CHAIN, "자", used_words)
    assert '"ㄱㄱㅁ"' in VllmService._build_prompt(GameType.CHOSUNG, "ㄱㄱㅁ", used_words)
    assert '"마"' in VllmService._build_prompt(GameType.CONTAINS, "마", used_words)
