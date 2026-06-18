from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.k6_preflight import load_env_file


DEFAULT_MIN_WORDS = 1000
DEFAULT_MIN_STARTS = 20


@dataclass(frozen=True)
class WordDbStats:
    active_word_count: int
    starts_with_count: int


@dataclass(frozen=True)
class WordDbCheck:
    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class WordDbReport:
    checks: list[WordDbCheck]

    @property
    def ok(self) -> bool:
        """DB의 끝말잇기 단어 seed가 k6 실행에 충분한지 반환합니다."""
        return all(check.ok for check in self.checks)


StatsGetter = Callable[[str, float], WordDbStats]


def build_database_url(env: Mapping[str, str]) -> str:
    """BE_DB_* 환경변수로 asyncpg가 사용할 PostgreSQL 접속 URL을 만듭니다."""
    missing = [
        key
        for key in ("BE_DB_HOST", "BE_DB_PORT", "BE_DB_USER", "BE_DB_PASSWORD", "BE_DB_NAME")
        if not env.get(key)
    ]
    if missing:
        raise ValueError("Missing required database environment variables: " + ", ".join(missing))
    user = quote(str(env["BE_DB_USER"]), safe="")
    password = quote(str(env["BE_DB_PASSWORD"]), safe="")
    host = str(env["BE_DB_HOST"])
    port = str(env["BE_DB_PORT"])
    name = quote(str(env["BE_DB_NAME"]), safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def build_word_db_report(
    *,
    env: Mapping[str, str],
    min_words: int = DEFAULT_MIN_WORDS,
    min_starts: int = DEFAULT_MIN_STARTS,
    timeout: float = 5.0,
    get_stats: StatsGetter | None = None,
) -> WordDbReport:
    """word_game.valid_words seed가 부하테스트에 충분한지 점검합니다."""
    database_url = build_database_url(env)
    stats_getter = get_stats or get_word_db_stats
    try:
        stats = stats_getter(database_url, timeout)
    except Exception as exc:
        return WordDbReport(
            checks=[
                WordDbCheck(
                    "database",
                    False,
                    f"database check failed: {exc}",
                )
            ]
        )
    seed_hint = "run mise run load-test-seed-valid-words before smoke"
    return WordDbReport(
        checks=[
            WordDbCheck(
                "active-word-count",
                stats.active_word_count >= min_words,
                f"active word_chain words={stats.active_word_count} min={min_words}; {seed_hint}",
            ),
            WordDbCheck(
                "starts-with-count",
                stats.starts_with_count >= min_starts,
                f"distinct starts_with={stats.starts_with_count} min={min_starts}; {seed_hint}",
            ),
        ]
    )


def get_word_db_stats(database_url: str, timeout: float) -> WordDbStats:
    """동기 CLI 흐름에서 async DB 점검을 실행합니다."""
    return asyncio.run(_get_word_db_stats(database_url, timeout))


async def _get_word_db_stats(database_url: str, timeout: float) -> WordDbStats:
    connection = await asyncpg.connect(database_url, timeout=timeout)
    try:
        row = await connection.fetchrow(
            """
            SELECT
                COUNT(*)::int AS active_word_count,
                COUNT(DISTINCT starts_with)::int AS starts_with_count
            FROM word_game.valid_words
            WHERE game_type = 'word_chain'
              AND is_active IS TRUE
            """
        )
    finally:
        await connection.close()
    return WordDbStats(
        active_word_count=int(row["active_word_count"] if row else 0),
        starts_with_count=int(row["starts_with_count"] if row else 0),
    )


def format_word_db_report(report: WordDbReport) -> str:
    """터미널에서 읽기 쉬운 valid word DB 점검 결과를 만듭니다."""
    lines = ["k6 valid word DB check"]
    for check in report.checks:
        status = "OK" if check.ok else "FAIL"
        lines.append(f"[{status}] {check.name}: {check.message}")
    lines.append(f"summary: ok={str(report.ok).lower()} checks={len(report.checks)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check word_game.valid_words before k6 tests.")
    parser.add_argument("--env-file", type=Path, default=Path(".env.load-test"))
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    parser.add_argument("--min-starts", type=int, default=DEFAULT_MIN_STARTS)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    try:
        env = load_env_file(args.env_file, base_env=os.environ)
        report = build_word_db_report(
            env=env,
            min_words=args.min_words,
            min_starts=args.min_starts,
            timeout=args.timeout,
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    print(format_word_db_report(report))
    raise SystemExit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
