from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_result_markdown(*, scenario: str, test_id: str, created_at: str) -> str:
    """k6 기준선 실행 결과를 사람이 채울 수 있는 Markdown 템플릿으로 만듭니다."""
    return f"""# k6 Load Test Result: {test_id}

## Run Metadata

- Scenario: `{scenario}`
- Test ID: `{test_id}`
- Created at: `{created_at}`
- Command:

```bash
.venv/bin/python scripts/run_k6_load_test.py {scenario} --test-id {test_id}
```

## Environment

- BE resource limit: `2 CPU / 4GB RAM`
- DB resource limit: `1 CPU / 2GB RAM`
- Agent target: private IP Agent URL from `AGENT_URL`
- k6 execution: Docker `k6-runner`
- Prometheus remote write: `http://prometheus:9090/api/v1/write`

## Preflight And Stack Check

- Preflight: `pass/fail`
- Stack check: `pass/fail`
- Notes:

## k6 Summary

| Metric | Value | Notes |
| --- | --- | --- |
| `http_req_failed` |  |  |
| `http_req_duration p95` |  |  |
| `http_req_duration p99` |  |  |
| `websocket_connect_success` |  |  |
| `e2e_cycle_duration p95` |  |  |
| `word_submit_attempts` |  |  |
| `word_submit_accepted_rate` |  |  |
| `word_submit_rejected_rate` |  |  |
| `word_pool_miss` |  |  |
| `vote_submit_attempts` |  |  |
| `vote_submit_accepted_rate` |  |  |
| `room_coordination_failures` |  |  |

## BE / DB / Agent Observations

- BE route latency:
- WebSocket close/error pattern:
- DB connection or CPU pressure:
- Agent latency/failure from `audit.agent` logs:
- Trace or Grafana links:

## Incidents

- Errors:
- Timeouts:
- Unexpected rejects:

## Baseline Decision

- Result: `usable / rerun-needed / blocked`
- SLO candidate:
- Next run adjustment:
"""


def write_result_template(
    *,
    root: Path,
    scenario: str,
    test_id: str,
    created_at: str,
    output: Path | None = None,
) -> Path:
    """결과 템플릿 파일을 생성하고 경로를 반환합니다."""
    output_path = output or root / "docs/load-testing/results" / f"{test_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_result_markdown(scenario=scenario, test_id=test_id, created_at=created_at),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a k6 load-test result template.")
    parser.add_argument("scenario")
    parser.add_argument("test_id")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    output_path = write_result_template(
        root=args.root,
        scenario=args.scenario,
        test_id=args.test_id,
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        output=args.output,
    )
    print(output_path)


if __name__ == "__main__":
    main()
