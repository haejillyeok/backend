import json
from pathlib import Path

import pytest

from scripts.seed_word_payloads import iter_payload_batches


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def word_payload(word: str) -> dict:
    return {
        "word": word,
        "start_word": word[0],
        "end_word": word[-1],
        "chosung": "ㄱㄱㄹ" if word == "가가린" else "ㅅㄱ",
        "syllables": list(word),
        "length": len(word),
        "used_count": 0,
    }


def test_iter_payload_batches_validates_and_batches_jsonl(tmp_path: Path) -> None:
    file = tmp_path / "words.jsonl"
    write_jsonl(file, [word_payload("가가린"), word_payload("사과")])

    batches = list(iter_payload_batches(file, batch_size=1))

    assert batches == [[word_payload("가가린")], [word_payload("사과")]]


def test_iter_payload_batches_rejects_derived_field_mismatch(tmp_path: Path) -> None:
    file = tmp_path / "words.jsonl"
    payload = word_payload("가가린")
    payload["end_word"] = "가"
    write_jsonl(file, [payload])

    with pytest.raises(ValueError, match="derived fields do not match"):
        list(iter_payload_batches(file, batch_size=500))


def test_iter_payload_batches_rejects_duplicate_words(tmp_path: Path) -> None:
    file = tmp_path / "words.jsonl"
    payload = word_payload("가가린")
    write_jsonl(file, [payload, payload])

    with pytest.raises(ValueError, match="duplicate word"):
        list(iter_payload_batches(file, batch_size=500))
