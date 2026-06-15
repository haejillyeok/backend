import pytest

from scripts.seed_valid_words import (
    build_valid_word_row,
    build_valid_words_seed_sql,
    iter_valid_word_row_batches,
)


def payload(word: str) -> dict:
    return {
        "word": word,
        "start_word": word[0],
        "end_word": word[-1],
        "chosung": "ㅅㄱ" if word == "사과" else "ㄱㄱㄹ",
        "syllables": list(word),
        "length": len(word),
        "used_count": 0,
    }


def test_build_valid_word_row_maps_jsonl_payload_to_dictionary_table() -> None:
    row = build_valid_word_row(payload("사과"), source="local-seed")

    assert row == {
        "game_type": "word_chain",
        "word": "사과",
        "normalized_word": "사과",
        "starts_with": "사",
        "ends_with": "과",
        "chosung": "ㅅㄱ",
        "syllables": ["사", "과"],
        "length": 2,
        "used_count": 0,
        "is_active": True,
        "source": "local-seed",
    }


def test_iter_valid_word_row_batches_reuses_payload_validation(tmp_path) -> None:
    file = tmp_path / "words.jsonl"
    file.write_text(
        "\n".join(
            [
                '{"word":"가가린","start_word":"가","end_word":"린","chosung":"ㄱㄱㄹ","syllables":["가","가","린"],"length":3,"used_count":0}',
                '{"word":"사과","start_word":"사","end_word":"과","chosung":"ㅅㄱ","syllables":["사","과"],"length":2,"used_count":0}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    batches = list(iter_valid_word_row_batches(file, batch_size=1, source="local-seed"))

    assert len(batches) == 2
    assert batches[0][0]["normalized_word"] == "가가린"
    assert batches[1][0]["normalized_word"] == "사과"


def test_iter_valid_word_row_batches_rejects_invalid_payload(tmp_path) -> None:
    file = tmp_path / "words.jsonl"
    file.write_text(
        '{"word":"사과","start_word":"사","end_word":"사","chosung":"ㅅㄱ","syllables":["사","과"],"length":2,"used_count":0}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="derived fields do not match"):
        list(iter_valid_word_row_batches(file, batch_size=500, source="local-seed"))


def test_build_valid_words_seed_sql_outputs_upsert_statement() -> None:
    sql = build_valid_words_seed_sql([build_valid_word_row(payload("사과"), source="local-seed")])

    assert "INSERT INTO word_game.valid_words" in sql
    assert "game_type" in sql
    assert "chosung" in sql
    assert "syllables" in sql
    assert '\'["사", "과"]\'::jsonb' in sql
    assert "ON CONFLICT (game_type, normalized_word) DO UPDATE SET" in sql
    assert "used_count = EXCLUDED.used_count" in sql
