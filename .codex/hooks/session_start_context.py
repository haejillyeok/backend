#!/usr/bin/env python3
"""세션 시작 시 Codex 작업 컨텍스트의 진입점을 안내한다."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _repo_root() -> Path:
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path.cwd(),
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()
    return Path(output.strip())


ROOT = _repo_root()


def _latest_markdown(directory: Path, *, limit: int = 3) -> list[Path]:
    if not directory.exists():
        return []
    files = [
        path
        for path in directory.glob("*.md")
        if path.name not in {"index.md", "template.md"}
    ]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def _status(path: Path) -> str:
    return "ok" if path.exists() else "missing"


def main() -> int:
    context = ROOT / ".codex" / "workflow" / "CONTEXT.md"
    state = ROOT / ".codex" / "workflow" / "STATE.md"
    wiki_index = ROOT / "llm-wiki" / "index.md"
    adr_dir = ROOT / "docs" / "adr"
    postmortem_dir = ROOT / "docs" / "postmortems"

    print("[Codex workflow]")
    print(f"- Context entrypoint: {context.relative_to(ROOT)} ({_status(context)})")
    print(f"- Workflow state: {state.relative_to(ROOT)} ({_status(state)})")
    print(f"- LLM wiki index: {wiki_index.relative_to(ROOT)} ({_status(wiki_index)})")

    latest_adrs = _latest_markdown(adr_dir)
    if latest_adrs:
        print("- Recent ADRs:")
        for path in latest_adrs:
            print(f"  - {path.relative_to(ROOT)}")
    else:
        print("- Recent ADRs: none")

    latest_postmortems = _latest_markdown(postmortem_dir)
    if latest_postmortems:
        print("- Recent postmortems:")
        for path in latest_postmortems:
            print(f"  - {path.relative_to(ROOT)}")
    else:
        print("- Recent postmortems: none")

    print(
        "- Start by reading llm-wiki/index.md and .codex/workflow/CONTEXT.md; "
        "create ADRs in docs/adr/ or postmortems in docs/postmortems/ when the workflow gates say so."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
