from app.agent.services.vllm import VllmService


def test_generated_shiritori_word_validation() -> None:
    validator = VllmService._is_valid_shiritori_word

    assert validator("자전거", condition="자", used_words=set())
    assert not validator("자동차", condition="자", used_words={"자동차"})
    assert not validator("기차", condition="자", used_words=set())
    assert not validator("자", condition="자", used_words=set())
    assert not validator("자전거놀이", condition="자", used_words=set())
    assert not validator("자전1", condition="자", used_words=set())
