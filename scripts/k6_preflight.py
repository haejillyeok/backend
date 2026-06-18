from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Status = Literal["ok", "warn", "fail"]


REQUIRED_FILES = (
    "docker-compose.yml",
    "docker-compose.load-test.yml",
    "k6/scenarios/smoke.js",
    "k6/scenarios/ramp-e2e.js",
    "k6/scenarios/soak-e2e.js",
)
WORD_FIXTURE_PATH = Path("k6/fixtures/word-pool.js")


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: Status
    message: str

    @property
    def ok(self) -> bool:
        """실행 중단이 필요한 실패인지 여부를 반환합니다."""
        return self.status != "fail"


@dataclass(frozen=True)
class PreflightReport:
    checks: list[PreflightCheck]

    @property
    def ok(self) -> bool:
        """모든 필수 점검이 smoke 실행 가능한 상태인지 반환합니다."""
        return all(check.ok for check in self.checks)

    @property
    def status_counts(self) -> dict[str, int]:
        """CLI 출력과 테스트에서 쓰는 상태별 점검 개수를 반환합니다."""
        counts = Counter(check.status for check in self.checks)
        return {status: counts[status] for status in ("ok", "warn", "fail")}


def build_preflight_report(
    *,
    root: Path,
    env: Mapping[str, str],
    which: Callable[[str], str | None] = shutil.which,
    run_command: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] | None = None,
) -> PreflightReport:
    """k6 smoke 실행 전 필요한 로컬 조건을 점검해 보고서를 만듭니다."""
    command_runner = run_command or _run_command
    checks = [
        check_required_files(root),
        check_word_fixture(root),
        check_agent_url(env),
        check_host_k6(which),
        check_docker_cli(which),
        check_docker_daemon(which, command_runner),
    ]
    return PreflightReport(checks=checks)


def check_required_files(root: Path) -> PreflightCheck:
    """load-test 실행에 필요한 문서화된 파일들이 있는지 확인합니다."""
    missing = [path for path in REQUIRED_FILES if not (root / path).exists()]
    if missing:
        return PreflightCheck(
            name="required-files",
            status="fail",
            message=f"required load-test files are missing: {', '.join(missing)}",
        )
    return PreflightCheck(
        name="required-files",
        status="ok",
        message="required load-test files exist",
    )


def check_word_fixture(root: Path) -> PreflightCheck:
    """k6가 사용할 끝말잇기 valid word fixture가 유효한지 확인합니다."""
    fixture_path = root / WORD_FIXTURE_PATH
    if not fixture_path.exists():
        return PreflightCheck(
            name="word-fixture",
            status="fail",
            message="word fixture is missing; run .venv/bin/python scripts/generate_k6_word_fixture.py",
        )
    try:
        fixture = _load_word_fixture(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return PreflightCheck(
            name="word-fixture",
            status="fail",
            message=f"word fixture is not a valid k6 JS module fixture: {exc}",
        )
    if not isinstance(fixture, dict) or not fixture:
        return PreflightCheck(
            name="word-fixture",
            status="fail",
            message="word fixture has no starts_with groups",
        )
    if not any(_has_valid_word_entry(words) for words in fixture.values()):
        return PreflightCheck(
            name="word-fixture",
            status="fail",
            message="word fixture has no usable word entries",
        )
    return PreflightCheck(
        name="word-fixture",
        status="ok",
        message=f"word fixture is ready at {WORD_FIXTURE_PATH}",
    )


def check_agent_url(env: Mapping[str, str]) -> PreflightCheck:
    """BE가 원격 Agent private IP를 호출할 수 있도록 AGENT_URL 설정을 확인합니다."""
    agent_url = env.get("AGENT_URL", "").strip()
    if not agent_url:
        return PreflightCheck(
            name="agent-url",
            status="fail",
            message="AGENT_URL is not set; set the private IP Agent URL before running load tests",
        )
    if not agent_url.startswith(("http://", "https://")):
        return PreflightCheck(
            name="agent-url",
            status="fail",
            message="AGENT_URL must start with http:// or https://",
        )
    return PreflightCheck(
        name="agent-url",
        status="ok",
        message="AGENT_URL is set",
    )


def _load_word_fixture(fixture_text: str) -> object:
    """k6 JS module 형태의 끝말잇기 fixture에서 JSON payload를 읽습니다."""
    text = fixture_text.strip()
    prefix = "export default "
    if text.startswith(prefix):
        text = text[len(prefix) :].strip()
    if text.endswith(";"):
        text = text[:-1].strip()
    return json.loads(text)


def check_host_k6(which: Callable[[str], str | None]) -> PreflightCheck:
    """호스트 k6 CLI가 있는지 확인하되 Docker runner 대체 경로를 허용합니다."""
    if which("k6"):
        return PreflightCheck(name="host-k6", status="ok", message="host k6 CLI is available")
    return PreflightCheck(
        name="host-k6",
        status="warn",
        message="host k6 CLI not found; use docker compose run --rm k6-runner instead",
    )


def check_docker_cli(which: Callable[[str], str | None]) -> PreflightCheck:
    """Docker 기반 k6 runner와 compose stack 실행에 필요한 Docker CLI를 확인합니다."""
    if which("docker"):
        return PreflightCheck(name="docker-cli", status="ok", message="Docker CLI is available")
    return PreflightCheck(
        name="docker-cli",
        status="fail",
        message="Docker CLI is not available",
    )


def check_docker_daemon(
    which: Callable[[str], str | None],
    run_command: Callable[[Sequence[str]], subprocess.CompletedProcess[str]],
) -> PreflightCheck:
    """Docker daemon이 실제로 켜져 있는지 확인합니다."""
    if not which("docker"):
        return PreflightCheck(
            name="docker-daemon",
            status="fail",
            message="Docker daemon cannot be checked because Docker CLI is missing",
        )
    result = run_command(["docker", "info"])
    if result.returncode == 0:
        return PreflightCheck(
            name="docker-daemon",
            status="ok",
            message="Docker daemon is reachable",
        )
    detail = (result.stderr or result.stdout or "unknown docker error").strip()
    return PreflightCheck(
        name="docker-daemon",
        status="fail",
        message=f"Docker daemon is not reachable: {detail}",
    )


def format_report(report: PreflightReport) -> str:
    """터미널에서 읽기 쉬운 preflight 결과 문자열을 만듭니다."""
    lines = ["k6 load-test preflight"]
    for check in report.checks:
        lines.append(f"[{check.status.upper()}] {check.name}: {check.message}")
    counts = report.status_counts
    lines.append(f"summary: ok={counts['ok']} warn={counts['warn']} fail={counts['fail']}")
    return "\n".join(lines)


def load_env_file(env_path: Path, *, base_env: Mapping[str, str]) -> dict[str, str]:
    """dotenv 형식의 key=value 파일을 읽어 기존 환경변수에 보충합니다."""
    if not env_path.exists():
        raise FileNotFoundError(
            f"load-test env file not found: {env_path}; "
            "copy .env.load-test.example to .env.load-test and set AGENT_URL"
        )
    env = dict(base_env)
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description="Check local prerequisites for k6 load tests.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args()

    try:
        env = (
            load_env_file(args.env_file, base_env=os.environ) if args.env_file else dict(os.environ)
        )
    except FileNotFoundError as exc:
        parser.error(str(exc))
    report = build_preflight_report(root=args.root, env=env)
    print(format_report(report))
    raise SystemExit(0 if report.ok else 1)


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _has_valid_word_entry(words: object) -> bool:
    if not isinstance(words, list):
        return False
    return any(
        isinstance(item, dict)
        and isinstance(item.get("normalized_word"), str)
        and isinstance(item.get("ends_with"), str)
        for item in words
    )


if __name__ == "__main__":
    main()
