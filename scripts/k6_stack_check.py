from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class EndpointCheckResult:
    url: str
    ok: bool
    status_code: int | None
    error: str | None = None


@dataclass(frozen=True)
class StackCheck:
    name: str
    result: EndpointCheckResult

    @property
    def ok(self) -> bool:
        """해당 endpoint가 smoke 실행 전 기대 상태인지 반환합니다."""
        return self.result.ok


@dataclass(frozen=True)
class StackReport:
    checks: list[StackCheck]

    @property
    def ok(self) -> bool:
        """모든 stack endpoint가 smoke 실행 가능한 상태인지 반환합니다."""
        return all(check.ok for check in self.checks)

    @property
    def status_counts(self) -> dict[str, int]:
        """CLI 출력과 테스트에서 쓰는 상태별 endpoint 개수를 반환합니다."""
        counts = Counter("ok" if check.ok else "fail" for check in self.checks)
        return {"ok": counts["ok"], "fail": counts["fail"]}


EndpointGetter = Callable[[str, float], EndpointCheckResult]


def build_stack_report(
    *,
    base_url: str,
    prometheus_url: str,
    coordinator_url: str,
    timeout: float = 3.0,
    get: EndpointGetter | None = None,
) -> StackReport:
    """load-test stack의 BE, Agent proxy, Prometheus, coordinator endpoint를 점검합니다."""
    endpoint_getter = get or get_endpoint
    endpoints = [
        ("be-root-health", f"{base_url.rstrip('/')}/health"),
        ("be-health", f"{base_url.rstrip('/')}/api/v1/health"),
        ("be-agent-health", f"{base_url.rstrip('/')}/api/v1/agent/health"),
        ("prometheus-ready", f"{prometheus_url.rstrip('/')}/-/ready"),
        ("k6-coordinator", f"{coordinator_url.rstrip('/')}/health"),
    ]
    return StackReport(
        checks=[
            StackCheck(name=name, result=endpoint_getter(url, timeout)) for name, url in endpoints
        ]
    )


def format_stack_report(report: StackReport) -> str:
    """터미널에서 읽기 쉬운 stack health 결과 문자열을 만듭니다."""
    lines = ["k6 load-test stack check"]
    for check in report.checks:
        status = "OK" if check.ok else "FAIL"
        detail = f"status={check.result.status_code}" if check.result.status_code else "no status"
        if check.result.error:
            detail = f"{detail} error={check.result.error}"
        lines.append(f"[{status}] {check.name}: {check.result.url} ({detail})")
    counts = report.status_counts
    lines.append(f"summary: ok={counts['ok']} fail={counts['fail']}")
    return "\n".join(lines)


def get_endpoint(url: str, timeout: float) -> EndpointCheckResult:
    """단일 HTTP endpoint를 GET으로 확인합니다."""
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
            return EndpointCheckResult(
                url=url,
                ok=200 <= status_code < 300,
                status_code=status_code,
            )
    except urllib.error.HTTPError as exc:
        return EndpointCheckResult(
            url=url,
            ok=False,
            status_code=exc.code,
            error=str(exc.reason),
        )
    except urllib.error.URLError as exc:
        return EndpointCheckResult(
            url=url,
            ok=False,
            status_code=None,
            error=str(exc.reason),
        )
    except TimeoutError:
        return EndpointCheckResult(url=url, ok=False, status_code=None, error="timeout")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check running local k6 load-test stack.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:9090")
    parser.add_argument("--coordinator-url", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    report = build_stack_report(
        base_url=args.base_url,
        prometheus_url=args.prometheus_url,
        coordinator_url=args.coordinator_url,
        timeout=args.timeout,
    )
    print(format_stack_report(report))
    raise SystemExit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
