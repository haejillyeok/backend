from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass


DEFAULT_METRIC_GROUPS: dict[str, list[str]] = {
    "word-submit": [
        "k6_word_submit_attempts_total",
        "word_submit_attempts_total",
        "k6_word_submit_attempts",
        "word_submit_attempts",
    ],
    "word-accepted-rate": [
        "k6_word_submit_accepted_rate_rate",
        "k6_word_submit_accepted_rate",
        "word_submit_accepted_rate_rate",
        "word_submit_accepted_rate",
    ],
    "websocket": [
        "k6_websocket_connect_success_rate",
        "k6_websocket_connect_success",
        "websocket_connect_success_rate",
        "websocket_connect_success",
    ],
    "cycle-duration": [
        "k6_e2e_cycle_duration_avg",
        "k6_e2e_cycle_duration_p95",
        "k6_e2e_cycle_duration",
        "e2e_cycle_duration_avg",
        "e2e_cycle_duration_p95",
        "e2e_cycle_duration",
    ],
}


@dataclass(frozen=True)
class PrometheusMetricCheck:
    name: str
    candidates: list[str]
    query: str | None
    series_count: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        """해당 metric group이 지정한 testid에서 발견됐는지 반환합니다."""
        return self.series_count > 0 and self.error is None


@dataclass(frozen=True)
class PrometheusMetricReport:
    test_id: str
    checks: list[PrometheusMetricCheck]

    @property
    def ok(self) -> bool:
        """필수 k6 metric group이 모두 Prometheus에 들어왔는지 반환합니다."""
        return all(check.ok for check in self.checks)


SeriesGetter = Callable[[str, str, float], list[dict[str, str]]]


def build_prometheus_metric_report(
    *,
    prometheus_url: str,
    test_id: str,
    groups: Mapping[str, Sequence[str]] | None = None,
    timeout: float = 3.0,
    get_series: SeriesGetter | None = None,
) -> PrometheusMetricReport:
    """testid label을 기준으로 Prometheus에 k6 metric series가 들어왔는지 확인합니다."""
    series_getter = get_series or get_prometheus_series
    checks: list[PrometheusMetricCheck] = []
    for name, candidates in (groups or DEFAULT_METRIC_GROUPS).items():
        checks.append(
            _check_metric_group(
                prometheus_url=prometheus_url,
                test_id=test_id,
                name=name,
                candidates=list(candidates),
                timeout=timeout,
                get_series=series_getter,
            )
        )
    return PrometheusMetricReport(test_id=test_id, checks=checks)


def get_prometheus_series(
    prometheus_url: str,
    query: str,
    timeout: float,
) -> list[dict[str, str]]:
    """Prometheus series API에서 단일 matcher의 series 목록을 가져옵니다."""
    params = urllib.parse.urlencode({"match[]": query})
    url = f"{prometheus_url.rstrip('/')}/api/v1/series?{params}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus returned status={payload.get('status')}")
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError("Prometheus series response data is not a list")
    return [series for series in data if isinstance(series, dict)]


def format_prometheus_metric_report(report: PrometheusMetricReport) -> str:
    """터미널에서 읽기 쉬운 Prometheus k6 metric 확인 결과를 만듭니다."""
    lines = [f"k6 Prometheus metric check: testid={report.test_id}"]
    for check in report.checks:
        status = "OK" if check.ok else "FAIL"
        detail = f"series={check.series_count}"
        if check.query:
            detail = f"{detail} query={check.query}"
        if check.error:
            detail = f"{detail} error={check.error}"
        lines.append(f"[{status}] {check.name}: {detail}")
    lines.append(f"summary: ok={str(report.ok).lower()} groups={len(report.checks)}")
    return "\n".join(lines)


def _check_metric_group(
    *,
    prometheus_url: str,
    test_id: str,
    name: str,
    candidates: list[str],
    timeout: float,
    get_series: SeriesGetter,
) -> PrometheusMetricCheck:
    for metric_name in candidates:
        query = f'{metric_name}{{testid="{test_id}"}}'
        try:
            series = get_series(prometheus_url, query, timeout)
        except (RuntimeError, urllib.error.URLError, TimeoutError) as exc:
            return PrometheusMetricCheck(
                name=name,
                candidates=candidates,
                query=query,
                series_count=0,
                error=str(exc),
            )
        if series:
            return PrometheusMetricCheck(
                name=name,
                candidates=candidates,
                query=query,
                series_count=len(series),
            )
    return PrometheusMetricCheck(
        name=name,
        candidates=candidates,
        query=f'{candidates[0]}{{testid="{test_id}"}}' if candidates else None,
        series_count=0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Check k6 remote-write metrics in Prometheus.")
    parser.add_argument("test_id")
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:9090")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    report = build_prometheus_metric_report(
        prometheus_url=args.prometheus_url,
        test_id=args.test_id,
        timeout=args.timeout,
    )
    print(format_prometheus_metric_report(report))
    raise SystemExit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
