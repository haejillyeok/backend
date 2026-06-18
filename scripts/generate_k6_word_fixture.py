from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_INPUT = Path("scripts/valid_words_seed.sql")
DEFAULT_OUTPUT = Path("k6/fixtures/word-pool.js")
DEFAULT_LIMIT_PER_START = 4


@dataclass(frozen=True)
class ValidWordFixtureRow:
    word: str
    normalized_word: str
    starts_with: str
    ends_with: str


def parse_seed_sql(sql_text: str) -> list[ValidWordFixtureRow]:
    rows: list[ValidWordFixtureRow] = []
    for raw_line in sql_text.splitlines():
        line = raw_line.strip().rstrip(",")
        if not line.startswith("(") or "::uuid" not in line:
            continue
        values = _parse_sql_tuple(line)
        if len(values) < 11:
            continue
        game_type = values[1]
        is_active = values[10]
        if game_type != "word_chain" or is_active is not True:
            continue
        rows.append(
            ValidWordFixtureRow(
                word=str(values[2]),
                normalized_word=str(values[3]),
                starts_with=str(values[4]),
                ends_with=str(values[5]),
            )
        )
    return rows


def build_fixture(
    rows: Iterable[ValidWordFixtureRow],
    *,
    limit_per_start: int | None = None,
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.starts_with, row.normalized_word)
        if key in seen:
            continue
        seen.add(key)
        grouped.setdefault(row.starts_with, []).append(
            {
                "word": row.word,
                "normalized_word": row.normalized_word,
                "ends_with": row.ends_with,
            }
        )
    fixture = {}
    for starts_with, words in sorted(grouped.items()):
        sorted_words = sorted(words, key=lambda item: item["normalized_word"])
        fixture[starts_with] = sorted_words[:limit_per_start] if limit_per_start else sorted_words
    return fixture


def write_fixture(fixture: dict[str, list[dict[str, str]]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "export default "
        + json.dumps(fixture, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + ";\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate k6 word-chain fixture JS module.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--limit-per-start",
        type=int,
        default=DEFAULT_LIMIT_PER_START,
        help="Maximum fixture words to keep per starts_with group; set 0 to keep all.",
    )
    args = parser.parse_args()

    rows = parse_seed_sql(args.input.read_text(encoding="utf-8"))
    limit_per_start = args.limit_per_start or None
    write_fixture(build_fixture(rows, limit_per_start=limit_per_start), args.output)


def _parse_sql_tuple(line: str) -> list[object]:
    normalized = line
    normalized = normalized.replace("::uuid", "")
    normalized = normalized.replace("::jsonb", "")
    normalized = normalized.replace("true", "True")
    normalized = normalized.replace("false", "False")
    return list(ast.literal_eval(normalized))


if __name__ == "__main__":
    main()
