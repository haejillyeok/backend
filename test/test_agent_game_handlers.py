import pytest

from app.agent.core.exceptions import InvalidGameCondition
from app.agent.schemas.request.answer import AgentAnswerRequest
from app.agent.services.game_handlers.chosung import ChosungHandler
from app.agent.services.game_handlers.contains import ContainsHandler
from app.agent.services.game_handlers.shiritori import ShiritoriHandler


def filter_values(query_filter) -> dict[str, object]:
    return {
        condition.key: condition.match.value
        for condition in query_filter.must
        if hasattr(condition.match, "value")
    }


def test_shiritori_filter_uses_fallback_and_excludes_used_words() -> None:
    request = AgentAnswerRequest(
        room_id="room-1",
        game_type="shiritori",
        used_words=["줄넘기"],
        last_char="줄",
    )
    query_filter = ShiritoriHandler().build_filter(request, {"줄넘기"})

    assert filter_values(query_filter)["start_word"] == "줄"
    assert set(filter_values(query_filter)) == {"start_word"}
    assert query_filter.must_not[0].key == "word"
    assert query_filter.must_not[0].match.any == ["줄넘기"]


def test_chosung_and_contains_filters() -> None:
    chosung_request = AgentAnswerRequest(
        room_id="room-1",
        game_type="chosung",
        used_words=[],
        condition={"chosung": "ㄱㄱㅁ"},
    )
    contains_request = AgentAnswerRequest(
        room_id="room-1",
        game_type="contains",
        used_words=[],
        condition={"contains_word": "마"},
    )

    assert (
        filter_values(ChosungHandler().build_filter(chosung_request, set()))["chosung"] == "ㄱㄱㅁ"
    )
    assert (
        filter_values(ContainsHandler().build_filter(contains_request, set()))["syllables"] == "마"
    )


def test_missing_game_condition_is_rejected() -> None:
    request = AgentAnswerRequest(
        room_id="room-1",
        game_type="chosung",
        used_words=[],
    )

    with pytest.raises(InvalidGameCondition):
        ChosungHandler().build_filter(request, set())
