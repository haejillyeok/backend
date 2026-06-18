from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.k6_db_word_check import WordDbReport, build_word_db_report, format_word_db_report
from scripts.k6_preflight import (
    PreflightReport,
    build_preflight_report,
    format_report,
    load_env_file,
)
from scripts.k6_stack_check import StackReport, build_stack_report, format_stack_report


ScenarioName = Literal["smoke", "ramp", "soak50", "soak100"]


SCENARIOS: dict[ScenarioName, dict[str, str]] = {
    "smoke": {
        "prefix": "local-smoke",
        "script": "k6/scenarios/smoke.js",
        "K6_ROOM_SIZE": "1",
    },
    "ramp": {"prefix": "local-ramp", "script": "k6/scenarios/ramp-e2e.js"},
    "soak50": {
        "prefix": "local-soak50",
        "script": "k6/scenarios/soak-e2e.js",
        "SOAK_VUS": "50",
        "SOAK_DURATION": "30m",
    },
    "soak100": {
        "prefix": "local-soak100",
        "script": "k6/scenarios/soak-e2e.js",
        "SOAK_VUS": "100",
        "SOAK_DURATION": "30m",
    },
}

K6_FORWARD_ENV_KEYS = (
    "BASE_URL",
    "BASE_WS_URL",
    "K6_COORDINATOR_URL",
    "K6_PROMETHEUS_RW_SERVER_URL",
    "K6_PROMETHEUS_RW_TREND_STATS",
    "K6_ROOM_SIZE",
    "K6_USER_PASSWORD",
    "MATCH_EVENT_WAIT_MS",
    "ROOM_MIX_ONE",
    "ROOM_MIX_TWO",
    "ROOM_MIX_THREE",
    "ROOM_MIX_FOUR",
    "SMOKE_DURATION",
    "SMOKE_ITERATIONS",
    "SMOKE_VUS",
    "SOAK_DURATION",
    "SOAK_VUS",
    "TURN_SUBMIT_DELAY_MS",
)


@dataclass(frozen=True)
class K6RunResult:
    exit_code: int
    command: list[str]
    env: dict[str, str]
    output: str


def build_k6_run_command(
    scenario: ScenarioName,
    test_id: str,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """문서화된 Docker k6 runner 명령을 scenario에 맞춰 조립합니다."""
    spec = SCENARIOS[scenario]
    command = [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.load-test.yml",
        "run",
        "--rm",
        "-e",
        f"TEST_ID={test_id}",
    ]
    for key, value in k6_container_env(env or scenario_env(spec)).items():
        command.extend(["-e", f"{key}={value}"])
    command.extend(
        [
            "k6-runner",
            "run",
            "-o",
            "experimental-prometheus-rw",
            "--tag",
            f"testid={test_id}",
            spec["script"],
        ]
    )
    return command


def run_k6_load_test(
    *,
    scenario: ScenarioName,
    root: Path,
    env: Mapping[str, str],
    test_id: str | None,
    dry_run: bool,
    preflight: Callable[[Path, Mapping[str, str]], PreflightReport] | None = None,
    stack_check: Callable[[Mapping[str, str]], StackReport] | None = None,
    word_db_check: Callable[[Mapping[str, str]], WordDbReport] | None = None,
    run_command: Callable[[Sequence[str], Mapping[str, str]], subprocess.CompletedProcess[str]]
    | None = None,
) -> K6RunResult:
    """preflight 후 Docker k6 runner를 실행하거나 dry-run 결과를 반환합니다."""
    resolved_test_id = test_id or env.get("TEST_ID") or create_test_id(scenario)
    run_env = build_run_env(env, scenario, resolved_test_id)
    command = build_k6_run_command(scenario, resolved_test_id, run_env)
    report_builder = preflight or (lambda root, env: build_preflight_report(root=root, env=env))
    report = report_builder(root, run_env)
    preflight_output = format_report(report)
    if not report.ok:
        if dry_run:
            preflight_output = (
                f"{preflight_output}\ndry-run command:\n{format_shell_command(command)}"
            )
        return K6RunResult(
            exit_code=1,
            command=command,
            env=run_env,
            output=preflight_output,
        )
    if dry_run:
        output = f"{preflight_output}\ndry-run command:\n{format_shell_command(command)}"
        return K6RunResult(exit_code=0, command=command, env=run_env, output=output)

    stack_report_builder = stack_check or build_default_stack_report
    stack_report = stack_report_builder(run_env)
    stack_output = format_stack_report(stack_report)
    if not stack_report.ok:
        return K6RunResult(
            exit_code=1,
            command=command,
            env=run_env,
            output=f"{preflight_output}\n{stack_output}",
        )

    word_db_report_builder = word_db_check or build_default_word_db_report
    word_db_report = word_db_report_builder(run_env)
    word_db_output = format_word_db_report(word_db_report)
    if not word_db_report.ok:
        return K6RunResult(
            exit_code=1,
            command=command,
            env=run_env,
            output=f"{preflight_output}\n{stack_output}\n{word_db_output}",
        )

    command_runner = run_command or _run_command
    result = command_runner(command, run_env)
    output = "\n".join(
        part
        for part in (
            preflight_output,
            stack_output,
            word_db_output,
            result.stdout or "",
            result.stderr or "",
        )
        if part
    )
    return K6RunResult(
        exit_code=result.returncode,
        command=command,
        env=run_env,
        output=output,
    )


def build_run_env(env: Mapping[str, str], scenario: ScenarioName, test_id: str) -> dict[str, str]:
    """k6 runner에 넘길 환경변수를 현재 shell 환경과 scenario 옵션으로 구성합니다."""
    run_env = dict(env)
    run_env["TEST_ID"] = test_id
    spec = SCENARIOS[scenario]
    for key, value in scenario_env(spec).items():
        run_env.setdefault(key, value)
    return run_env


def scenario_env(spec: Mapping[str, str]) -> dict[str, str]:
    """k6 scenario별로 runner에 전달할 환경변수를 추출합니다."""
    reserved_keys = {"prefix", "script"}
    return {key: value for key, value in spec.items() if key not in reserved_keys}


def k6_container_env(env: Mapping[str, str]) -> dict[str, str]:
    """Docker k6 컨테이너 안으로 전달할 k6 runtime 환경변수만 추립니다."""
    return {key: str(env[key]) for key in K6_FORWARD_ENV_KEYS if key in env}


def load_run_env(*, base_env: Mapping[str, str], env_file: Path | None) -> dict[str, str]:
    """shell 환경변수에 load-test env 파일 값을 보충합니다."""
    return load_env_file(env_file, base_env=base_env) if env_file else dict(base_env)


def build_default_stack_report(env: Mapping[str, str]) -> StackReport:
    """Docker k6 wrapper 실행 전 호스트에서 노출된 stack endpoint를 확인합니다."""
    return build_stack_report(
        base_url=env.get("BASE_URL", "http://127.0.0.1:8000"),
        prometheus_url=env.get("PROMETHEUS_URL", "http://127.0.0.1:9090"),
        coordinator_url=env.get("K6_COORDINATOR_URL", "http://127.0.0.1:8787"),
    )


def build_default_word_db_report(env: Mapping[str, str]) -> WordDbReport:
    """Docker k6 wrapper 실행 전 DB valid word seed 적재 상태를 확인합니다."""
    return build_word_db_report(env=env)


def create_test_id(scenario: ScenarioName) -> str:
    """실행마다 구분 가능한 testid를 생성합니다."""
    return f"{SCENARIOS[scenario]['prefix']}-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def format_shell_command(command: Sequence[str]) -> str:
    """dry-run 출력용 shell command 문자열을 만듭니다."""
    return " ".join(command)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local k6 load-test scenarios.")
    parser.add_argument("scenario", choices=tuple(SCENARIOS))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--test-id", default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        env = load_run_env(base_env=os.environ, env_file=args.env_file)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    result = run_k6_load_test(
        scenario=args.scenario,
        root=args.root,
        env=env,
        test_id=args.test_id,
        dry_run=args.dry_run,
    )
    print(result.output)
    raise SystemExit(result.exit_code)


def _run_command(
    command: Sequence[str],
    env: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=Path.cwd(),
        env=_as_subprocess_env(env),
        capture_output=True,
        text=True,
        check=False,
    )


def _as_subprocess_env(env: Mapping[str, str]) -> MutableMapping[str, str]:
    return {str(key): str(value) for key, value in env.items()}


if __name__ == "__main__":
    main()
