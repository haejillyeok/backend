# k6 BE Load Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local k6 E2E load-testing harness for the BE server with Docker resource limits, valid word-chain submissions, multiplayer room coverage, and Prometheus/Grafana metrics.

**Architecture:** Keep the normal development stack unchanged and add a load-test-specific compose override plus k6 scripts. Python code generates a deterministic k6 word fixture from `scripts/valid_words_seed.sql`; a local-only coordinator service handles 2~4인 방 rendezvous outside product APIs. k6 JavaScript helpers execute auth, room, lobby WebSocket, match WebSocket, valid word submission, multiplayer coordination, and scenario orchestration.

**Tech Stack:** Docker Compose, FastAPI BE Docker image, PostgreSQL, Prometheus remote write, Grafana, k6 JavaScript, Python 3.11, pytest, PyYAML.

---

## Source Spec

- Human-facing plan: `docs/load-testing/k6-be-load-test-plan.md`
- API contracts: `docs/api.md`, `app/be/api/docs/ws-api.md`
- Runtime and observability rules: `llm-wiki/wiki/runtime-configuration.md`, `llm-wiki/wiki/observability-stack.md`

## File Structure

- Create `docker-compose.load-test.yml`: load-test-only compose override for resource limits, `be-loadtest`, local coordinator, Docker k6 runner, and Prometheus remote write receiver.
- Create `.env.load-test.example`: local load-test environment template for remote Agent URL, DB, OTEL, BE workers, and k6 image.
- Create `scripts/k6_coordinator.py`: local-only FastAPI coordinator for room assignment, room id exchange, ready tracking, and session id exchange.
- Create `scripts/k6_preflight.py`: local prerequisite checker for required files, word fixture, Agent URL, Docker daemon, and host k6/Docker runner path.
- Create `scripts/k6_stack_check.py`: local running-stack checker for BE health, Agent health proxy, Prometheus readiness, and k6 coordinator health.
- Create `scripts/k6_result_template.py`: Markdown result note generator for first baseline and later k6 runs.
- Create `scripts/run_k6_load_test.py`: local Docker k6 runner wrapper for smoke, ramp, 50 VU soak, and 100 VU soak scenarios.
- Create `test/test_k6_coordinator.py`: pytest coverage for 1~4인 방 assignment and lifecycle endpoints.
- Create `test/test_k6_preflight.py`: pytest coverage for preflight success and failure reports.
- Create `test/test_k6_stack_check.py`: pytest coverage for running-stack success and failed Agent health reports.
- Create `test/test_k6_result_template.py`: pytest coverage for result template content and default output path.
- Modify `.mise.toml`: add `load-test-*` tasks for stack startup, fixture generation, preflight, stack check, scenario runs, and result note creation.
- Create `test/test_load_test_mise_tasks.py`: pytest coverage for load-test mise task wiring.
- Create `test/test_load_test_env_example.py`: pytest coverage for load-test env example and gitignore tracking exception.
- Create `test/test_k6_run_wrapper.py`: pytest coverage for Docker k6 runner command construction, soak envs, dry-run, and preflight failure handling.
- Create `scripts/generate_k6_word_fixture.py`: parse `scripts/valid_words_seed.sql` into a starts-with grouped JSON fixture.
- Create `test/test_k6_word_fixture.py`: pytest coverage for fixture parsing, grouping, filtering, and output shape.
- Create `test/test_load_test_compose.py`: pytest coverage for compose override resource limits and Prometheus remote write flag.
- Create `test/test_k6_assets.py`: static repository guard for expected k6 scenario/helper files and key metric names.
- Create `k6/fixtures/word-pool.json`: generated valid word fixture committed for deterministic local k6 runs.
- Create `k6/lib/config.js`: environment parsing for base URLs, test IDs, room mix, credentials, and timing.
- Create `k6/lib/metrics.js`: custom k6 metrics shared by scenarios.
- Create `k6/lib/http.js`: small HTTP wrappers and response checks.
- Create `k6/lib/auth.js`: signup/login helper and session cookie extraction.
- Create `k6/lib/rooms.js`: room list/create/join/start/entry helper.
- Create `k6/lib/lobby-ws.js`: lobby WebSocket connect, initial event checks, and ping.
- Create `k6/lib/match-ws.js`: match WebSocket connect, snapshot handling, word submit, vote submit, event loop.
- Create `k6/lib/word-pool.js`: choose valid word-chain words by `required_start_char` and track per-cycle used words.
- Create `k6/lib/coordinator.js`: HTTP client for the local coordinator service.
- Create `k6/scenarios/smoke.js`: short E2E smoke scenario.
- Create `k6/scenarios/ramp-e2e.js`: 10 -> 50 -> 100 VU ramp scenario.
- Create `k6/scenarios/soak-e2e.js`: 50 VU default soak and 100 VU extended soak via environment options.
- Modify `docs/load-testing/k6-be-load-test-plan.md`: add exact run commands once files exist.
- Modify `docs/index.md`: already links the load-test plan; no extra index change is required unless a new docs page is added.

## Task 1: Load-Test Compose Override

**Files:**
- Create: `docker-compose.load-test.yml`
- Create: `test/test_load_test_compose.py`

- [ ] **Step 1: Write the failing compose test**

Create `test/test_load_test_compose.py`:

```python
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.load-test.yml"


def load_compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_load_test_compose_limits_postgres_and_be_resources() -> None:
    compose = load_compose()
    services = compose["services"]

    postgres = services["postgres"]
    be = services["be-loadtest"]

    assert postgres["cpus"] == "1.0"
    assert postgres["mem_limit"] == "2g"
    assert be["cpus"] == "2.0"
    assert be["mem_limit"] == "4g"


def test_load_test_compose_adds_be_loadtest_service() -> None:
    compose = load_compose()
    be = compose["services"]["be-loadtest"]

    assert be["image"] == "haejillyeok-backend:loadtest"
    assert be["build"]["context"] == "."
    assert be["build"]["dockerfile"] == "Dockerfile"
    assert be["environment"]["APP_MODULE"] == "be"
    assert be["environment"]["PORT"] == "8000"
    assert be["environment"]["BE_DB_HOST"] == "postgres"
    assert be["environment"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector:4318"
    assert "8000:8000" in be["ports"]
    assert be["depends_on"]["postgres"]["condition"] == "service_healthy"


def test_load_test_compose_adds_local_k6_coordinator_service() -> None:
    compose = load_compose()
    coordinator = compose["services"]["k6-coordinator"]

    assert coordinator["image"] == "haejillyeok-backend:loadtest"
    assert coordinator["command"] == "python scripts/k6_coordinator.py"
    assert coordinator["environment"]["K6_COORDINATOR_HOST"] == "0.0.0.0"
    assert coordinator["environment"]["K6_COORDINATOR_PORT"] == "8787"
    assert "8787:8787" in coordinator["ports"]


def test_load_test_compose_adds_docker_k6_runner_service() -> None:
    compose = load_compose()
    k6_runner = compose["services"]["k6-runner"]

    assert k6_runner["image"] == "${K6_IMAGE:-grafana/k6:0.49.0}"
    assert k6_runner["profiles"] == ["load-test-runner"]
    assert k6_runner["working_dir"] == "/loadtest"
    assert "./:/loadtest:ro" in k6_runner["volumes"]
    assert k6_runner["environment"]["BASE_URL"] == "http://be-loadtest:8000"
    assert k6_runner["environment"]["BASE_WS_URL"] == "ws://be-loadtest:8000"
    assert k6_runner["environment"]["K6_COORDINATOR_URL"] == "http://k6-coordinator:8787"
    assert (
        k6_runner["environment"]["K6_PROMETHEUS_RW_SERVER_URL"]
        == "http://prometheus:9090/api/v1/write"
    )
    assert k6_runner["depends_on"]["be-loadtest"]["condition"] == "service_started"
    assert k6_runner["depends_on"]["k6-coordinator"]["condition"] == "service_started"


def test_load_test_compose_enables_prometheus_remote_write_receiver() -> None:
    compose = load_compose()
    command = compose["services"]["prometheus"]["command"]

    assert "--web.enable-remote-write-receiver" in command
    assert "--web.enable-lifecycle" in command
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_load_test_compose.py -q -o addopts=''
```

Expected: FAIL because `docker-compose.load-test.yml` does not exist.

- [ ] **Step 3: Create minimal compose override**

Create `docker-compose.load-test.yml`:

```yaml
services:
  postgres:
    cpus: "1.0"
    mem_limit: 2g

  prometheus:
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--web.enable-lifecycle"
      - "--web.enable-remote-write-receiver"

  be-loadtest:
    image: haejillyeok-backend:loadtest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: haejillyeok-be-loadtest
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      otel-collector:
        condition: service_started
    environment:
      APP_MODULE: be
      BE_ENV: ${BE_ENV:-local}
      APP_TIMEZONE: ${APP_TIMEZONE:-Asia/Seoul}
      HOST: 0.0.0.0
      PORT: "8000"
      WORKERS: ${BE_LOADTEST_WORKERS:-1}
      BE_DB_HOST: postgres
      BE_DB_PORT: "5432"
      BE_DB_USER: ${BE_DB_USER:-haejillyeok}
      BE_DB_PASSWORD: ${BE_DB_PASSWORD:-haejillyeok}
      BE_DB_NAME: ${BE_DB_NAME:-haejillyeok}
      AGENT_URL: ${AGENT_URL}
      K3S_AGENT_KEY: ${K3S_AGENT_KEY}
      OTEL_ENABLED: ${OTEL_ENABLED:-true}
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4318
      OTEL_METRIC_EXPORT_INTERVAL: ${OTEL_METRIC_EXPORT_INTERVAL:-5000}
      LOG_FILE_ENABLED: ${LOG_FILE_ENABLED:-true}
      LOG_DIR: /app/logs
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
    cpus: "2.0"
    mem_limit: 4g

  k6-coordinator:
    image: haejillyeok-backend:loadtest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: haejillyeok-k6-coordinator
    restart: unless-stopped
    command: python scripts/k6_coordinator.py
    environment:
      K6_COORDINATOR_HOST: 0.0.0.0
      K6_COORDINATOR_PORT: "8787"
    ports:
      - "8787:8787"

  k6-runner:
    image: ${K6_IMAGE:-grafana/k6:0.49.0}
    profiles:
      - load-test-runner
    depends_on:
      be-loadtest:
        condition: service_started
      k6-coordinator:
        condition: service_started
      prometheus:
        condition: service_started
    working_dir: /loadtest
    environment:
      BASE_URL: http://be-loadtest:8000
      BASE_WS_URL: ws://be-loadtest:8000
      K6_COORDINATOR_URL: http://k6-coordinator:8787
      K6_PROMETHEUS_RW_SERVER_URL: http://prometheus:9090/api/v1/write
      K6_PROMETHEUS_RW_TREND_STATS: p(95),p(99),min,max,avg
    volumes:
      - ./:/loadtest:ro
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest test/test_load_test_compose.py -q -o addopts=''
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.load-test.yml test/test_load_test_compose.py
git commit -m "test: add load test compose override"
```

## Task 2: Valid Word Fixture Generator

**Files:**
- Create: `scripts/generate_k6_word_fixture.py`
- Create: `test/test_k6_word_fixture.py`
- Create: `k6/fixtures/word-pool.json`

- [ ] **Step 1: Write the failing fixture generator tests**

Create `test/test_k6_word_fixture.py`:

```python
import json
from pathlib import Path

from scripts.generate_k6_word_fixture import (
    ValidWordFixtureRow,
    build_fixture,
    parse_seed_sql,
    write_fixture,
)


SAMPLE_SQL = """
INSERT INTO word_game.valid_words (
    id,
    game_type,
    word,
    normalized_word,
    starts_with,
    ends_with,
    chosung,
    syllables,
    length,
    used_count,
    is_active,
    source
) VALUES
    ('00000000-0000-0000-0000-000000000001'::uuid, 'word_chain', '사과', '사과', '사', '과', 'ㅅㄱ', '["사", "과"]'::jsonb, 2, 0, true, 'sample'),
    ('00000000-0000-0000-0000-000000000002'::uuid, 'word_chain', '가구', '가구', '가', '구', 'ㄱㄱ', '["가", "구"]'::jsonb, 2, 0, true, 'sample'),
    ('00000000-0000-0000-0000-000000000003'::uuid, 'contains', '가나', '가나', '가', '나', 'ㄱㄴ', '["가", "나"]'::jsonb, 2, 0, true, 'sample'),
    ('00000000-0000-0000-0000-000000000004'::uuid, 'word_chain', '가방', '가방', '가', '방', 'ㄱㅂ', '["가", "방"]'::jsonb, 2, 0, false, 'sample')
ON CONFLICT (game_type, normalized_word) DO UPDATE SET
    starts_with = EXCLUDED.starts_with;
"""


def test_parse_seed_sql_reads_word_chain_active_rows() -> None:
    rows = parse_seed_sql(SAMPLE_SQL)

    assert rows == [
        ValidWordFixtureRow(word="사과", normalized_word="사과", starts_with="사", ends_with="과"),
        ValidWordFixtureRow(word="가구", normalized_word="가구", starts_with="가", ends_with="구"),
    ]


def test_build_fixture_groups_words_by_start_char_sorted_for_determinism() -> None:
    rows = [
        ValidWordFixtureRow(word="사과", normalized_word="사과", starts_with="사", ends_with="과"),
        ValidWordFixtureRow(word="가구", normalized_word="가구", starts_with="가", ends_with="구"),
        ValidWordFixtureRow(word="가나", normalized_word="가나", starts_with="가", ends_with="나"),
    ]

    fixture = build_fixture(rows)

    assert list(fixture) == ["가", "사"]
    assert fixture["가"] == [
        {"word": "가구", "normalized_word": "가구", "ends_with": "구"},
        {"word": "가나", "normalized_word": "가나", "ends_with": "나"},
    ]


def test_write_fixture_outputs_utf8_json(tmp_path: Path) -> None:
    output_path = tmp_path / "word-pool.json"
    fixture = {
        "사": [{"word": "사과", "normalized_word": "사과", "ends_with": "과"}],
    }

    write_fixture(fixture, output_path)

    assert json.loads(output_path.read_text(encoding="utf-8")) == fixture
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_word_fixture.py -q -o addopts=''
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.generate_k6_word_fixture'`.

- [ ] **Step 3: Implement fixture generator**

Create `scripts/generate_k6_word_fixture.py`:

```python
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_INPUT = Path("scripts/valid_words_seed.sql")
DEFAULT_OUTPUT = Path("k6/fixtures/word-pool.json")


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


def build_fixture(rows: Iterable[ValidWordFixtureRow]) -> dict[str, list[dict[str, str]]]:
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
    return {
        starts_with: sorted(words, key=lambda item: item["normalized_word"])
        for starts_with, words in sorted(grouped.items())
    }


def write_fixture(fixture: dict[str, list[dict[str, str]]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate k6 word-chain fixture JSON.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = parse_seed_sql(args.input.read_text(encoding="utf-8"))
    write_fixture(build_fixture(rows), args.output)


def _parse_sql_tuple(line: str) -> list[object]:
    normalized = line
    normalized = normalized.replace("::uuid", "")
    normalized = normalized.replace("::jsonb", "")
    normalized = normalized.replace("true", "True")
    normalized = normalized.replace("false", "False")
    return list(ast.literal_eval(normalized))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_word_fixture.py -q -o addopts=''
```

Expected: PASS.

- [ ] **Step 5: Generate committed fixture**

Run:

```bash
.venv/bin/python scripts/generate_k6_word_fixture.py
```

Expected: `k6/fixtures/word-pool.json` exists and contains Korean keys such as `"가"`, `"사"`.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_k6_word_fixture.py test/test_k6_word_fixture.py k6/fixtures/word-pool.json
git commit -m "feat: add k6 word fixture generator"
```

## Task 3: k6 Shared Config, Metrics, and Word Pool Helpers

**Files:**
- Create: `k6/lib/config.js`
- Create: `k6/lib/metrics.js`
- Create: `k6/lib/word-pool.js`
- Create: `test/test_k6_assets.py`

- [ ] **Step 1: Write failing static asset tests**

Create `test/test_k6_assets.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_k6_shared_helpers_define_expected_metrics_and_word_pool_functions() -> None:
    metrics = read("k6/lib/metrics.js")
    word_pool = read("k6/lib/word-pool.js")

    assert "word_submit_attempts" in metrics
    assert "word_submit_accepted_rate" in metrics
    assert "word_pool_miss" in metrics
    assert "word_submit_latency" in metrics
    assert "function createWordPicker" in word_pool
    assert "function pickWordForTurn" in word_pool


def test_k6_config_exposes_base_urls_and_testid() -> None:
    config = read("k6/lib/config.js")

    assert "BASE_URL" in config
    assert "BASE_WS_URL" in config
    assert "TEST_ID" in config
    assert "ROOM_MIX" in config
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_assets.py -q -o addopts=''
```

Expected: FAIL because `k6/lib/*.js` files do not exist.

- [ ] **Step 3: Implement config and metrics helpers**

Create `k6/lib/config.js`:

```javascript
export const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';
export const BASE_WS_URL = __ENV.BASE_WS_URL || BASE_URL.replace(/^http/, 'ws');
export const TEST_ID = __ENV.TEST_ID || `local-${Date.now()}`;
export const PASSWORD = __ENV.K6_USER_PASSWORD || 'Loadtest123!';
export const ROOM_MIX = Object.freeze({
  one: Number(__ENV.ROOM_MIX_ONE || 50),
  two: Number(__ENV.ROOM_MIX_TWO || 20),
  three: Number(__ENV.ROOM_MIX_THREE || 15),
  four: Number(__ENV.ROOM_MIX_FOUR || 15),
});
export const TURN_SUBMIT_DELAY_MS = Number(__ENV.TURN_SUBMIT_DELAY_MS || 250);
export const MATCH_EVENT_WAIT_MS = Number(__ENV.MATCH_EVENT_WAIT_MS || 15000);
```

Create `k6/lib/metrics.js`:

```javascript
import { Counter, Rate, Trend } from 'k6/metrics';

export const e2eCycleDuration = new Trend('e2e_cycle_duration', true);
export const roomCoordinationFailures = new Counter('room_coordination_failures');
export const websocketConnectSuccess = new Rate('websocket_connect_success');
export const websocketPingDuration = new Trend('websocket_ping_duration', true);
export const wordSubmitAttempts = new Counter('word_submit_attempts');
export const wordSubmitAcceptedRate = new Rate('word_submit_accepted_rate');
export const wordSubmitRejectedRate = new Rate('word_submit_rejected_rate');
export const wordSubmitTimeoutRate = new Rate('word_submit_timeout_rate');
export const wordSubmitFailedRate = new Rate('word_submit_failed_rate');
export const wordPoolMiss = new Counter('word_pool_miss');
export const wordSubmitLatency = new Trend('word_submit_latency', true);
```

- [ ] **Step 4: Implement word pool helper**

Create `k6/lib/word-pool.js`:

```javascript
import wordPool from '../fixtures/word-pool.json';
import { wordPoolMiss } from './metrics.js';

export function createWordPicker() {
  return {
    usedByRound: {},
    offsets: {},
  };
}

export function pickWordForTurn(picker, turn) {
  const required = turn && turn.required_start_char;
  if (!required) {
    return null;
  }
  const candidates = wordPool[required] || [];
  if (candidates.length === 0) {
    wordPoolMiss.add(1, { required_start_char: required });
    return null;
  }
  const roundKey = String(turn.round_number || 1);
  const used = picker.usedByRound[roundKey] || {};
  picker.usedByRound[roundKey] = used;
  const offsetKey = `${roundKey}:${required}`;
  const startOffset = picker.offsets[offsetKey] || 0;
  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[(startOffset + index) % candidates.length];
    if (!used[candidate.normalized_word]) {
      picker.offsets[offsetKey] = startOffset + index + 1;
      used[candidate.normalized_word] = true;
      return candidate;
    }
  }
  wordPoolMiss.add(1, { required_start_char: required });
  return null;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_assets.py -q -o addopts=''
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add k6/lib/config.js k6/lib/metrics.js k6/lib/word-pool.js test/test_k6_assets.py
git commit -m "feat: add k6 shared helpers"
```

## Task 4: Local Multiplayer Coordinator

**Files:**
- Create: `scripts/k6_coordinator.py`
- Create: `test/test_k6_coordinator.py`

- [ ] **Step 1: Write failing coordinator tests**

Create `test/test_k6_coordinator.py`:

```python
from fastapi.testclient import TestClient

from scripts.k6_coordinator import create_app


def test_coordinator_assigns_room_sizes_from_mix() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/assignments/claim",
        json={"test_id": "local", "vu": 1, "iteration": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["room_size"] in {1, 2, 3, 4}
    assert payload["slot_index"] >= 0
    assert payload["group_id"].startswith("local-")


def test_coordinator_exchanges_room_ready_and_session_state() -> None:
    client = TestClient(create_app())
    owner = client.post(
        "/assignments/claim",
        json={"test_id": "local", "vu": 1, "iteration": 0, "room_size": 2},
    ).json()
    guest = client.post(
        "/assignments/claim",
        json={"test_id": "local", "vu": 2, "iteration": 0, "room_size": 2},
    ).json()
    group_id = owner["group_id"]

    assert owner["slot_index"] == 0
    assert guest["slot_index"] == 1

    room_response = client.post(
        f"/groups/{group_id}/room",
        json={"room_public_id": "room-1"},
    )
    assert room_response.status_code == 200
    assert client.get(f"/groups/{group_id}/room").json()["room_public_id"] == "room-1"

    assert client.post(f"/groups/{group_id}/ready", json={"slot_index": 0}).status_code == 200
    assert client.post(f"/groups/{group_id}/ready", json={"slot_index": 1}).status_code == 200
    ready = client.get(f"/groups/{group_id}/ready").json()
    assert ready == {"ready_count": 2, "required_count": 2, "all_ready": True}

    session_response = client.post(
        f"/groups/{group_id}/session",
        json={"game_session_public_id": "session-1"},
    )
    assert session_response.status_code == 200
    assert client.get(f"/groups/{group_id}/session").json()["game_session_public_id"] == "session-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_coordinator.py -q -o addopts=''
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.k6_coordinator'`.

- [ ] **Step 3: Implement coordinator service**

Create `scripts/k6_coordinator.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class AssignmentRequest(BaseModel):
    test_id: str
    vu: int = Field(ge=1)
    iteration: int = Field(ge=0)
    room_size: int | None = Field(default=None, ge=1, le=4)


class RoomPayload(BaseModel):
    room_public_id: str


class ReadyPayload(BaseModel):
    slot_index: int = Field(ge=0)


class SessionPayload(BaseModel):
    game_session_public_id: str


@dataclass
class GroupState:
    group_id: str
    room_size: int
    room_public_id: str | None = None
    game_session_public_id: str | None = None
    claimed_slots: set[int] = field(default_factory=set)
    ready_slots: set[int] = field(default_factory=set)


def create_app() -> FastAPI:
    app = FastAPI(title="k6 local coordinator")
    groups: dict[str, GroupState] = {}

    @app.post("/assignments/claim")
    async def claim_assignment(request: AssignmentRequest) -> dict[str, object]:
        room_size = request.room_size or _choose_room_size(request.vu, request.iteration)
        group_number = (request.vu - 1) // room_size
        slot_index = (request.vu - 1) % room_size
        group_id = f"{request.test_id}-{room_size}-{request.iteration}-{group_number}"
        group = groups.setdefault(group_id, GroupState(group_id=group_id, room_size=room_size))
        group.claimed_slots.add(slot_index)
        return {
            "group_id": group_id,
            "room_size": room_size,
            "slot_index": slot_index,
            "is_owner": slot_index == 0,
        }

    @app.post("/groups/{group_id}/room")
    async def set_room(group_id: str, payload: RoomPayload) -> dict[str, str]:
        group = _get_group(groups, group_id)
        group.room_public_id = payload.room_public_id
        return {"room_public_id": payload.room_public_id}

    @app.get("/groups/{group_id}/room")
    async def get_room(group_id: str) -> dict[str, str | None]:
        group = _get_group(groups, group_id)
        return {"room_public_id": group.room_public_id}

    @app.post("/groups/{group_id}/ready")
    async def set_ready(group_id: str, payload: ReadyPayload) -> dict[str, object]:
        group = _get_group(groups, group_id)
        if payload.slot_index >= group.room_size:
            raise HTTPException(status_code=422, detail="slot_index exceeds room size")
        group.ready_slots.add(payload.slot_index)
        return _ready_payload(group)

    @app.get("/groups/{group_id}/ready")
    async def get_ready(group_id: str) -> dict[str, object]:
        return _ready_payload(_get_group(groups, group_id))

    @app.post("/groups/{group_id}/session")
    async def set_session(group_id: str, payload: SessionPayload) -> dict[str, str]:
        group = _get_group(groups, group_id)
        group.game_session_public_id = payload.game_session_public_id
        return {"game_session_public_id": payload.game_session_public_id}

    @app.get("/groups/{group_id}/session")
    async def get_session(group_id: str) -> dict[str, str | None]:
        group = _get_group(groups, group_id)
        return {"game_session_public_id": group.game_session_public_id}

    return app


def _choose_room_size(vu: int, iteration: int) -> int:
    bucket = (vu + iteration) % 20
    if bucket < 10:
        return 1
    if bucket < 14:
        return 2
    if bucket < 17:
        return 3
    return 4


def _get_group(groups: dict[str, GroupState], group_id: str) -> GroupState:
    group = groups.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    return group


def _ready_payload(group: GroupState) -> dict[str, object]:
    ready_count = len(group.ready_slots)
    return {
        "ready_count": ready_count,
        "required_count": group.room_size,
        "all_ready": ready_count >= group.room_size,
    }


app = create_app()


if __name__ == "__main__":
    host = os.getenv("K6_COORDINATOR_HOST", "127.0.0.1")
    port = int(os.getenv("K6_COORDINATOR_PORT", "8787"))
    uvicorn.run("scripts.k6_coordinator:app", host=host, port=port, log_level="info")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_coordinator.py -q -o addopts=''
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/k6_coordinator.py test/test_k6_coordinator.py
git commit -m "feat: add k6 local coordinator"
```

## Task 5: k6 HTTP, Auth, Room, Coordinator, and WebSocket Helpers

**Files:**
- Create: `k6/lib/http.js`
- Create: `k6/lib/auth.js`
- Create: `k6/lib/rooms.js`
- Create: `k6/lib/coordinator.js`
- Create: `k6/lib/lobby-ws.js`
- Create: `k6/lib/match-ws.js`
- Modify: `test/test_k6_assets.py`

- [ ] **Step 1: Extend failing asset tests**

Append to `test/test_k6_assets.py`:

```python
def test_k6_flow_helpers_include_required_api_paths_and_ws_messages() -> None:
    auth = read("k6/lib/auth.js")
    rooms = read("k6/lib/rooms.js")
    coordinator = read("k6/lib/coordinator.js")
    lobby = read("k6/lib/lobby-ws.js")
    match = read("k6/lib/match-ws.js")

    assert "/api/v1/auth/signup" in auth
    assert "/api/v1/auth/login" in auth
    assert "/api/v1/game/rooms" in rooms
    assert "/start" in rooms
    assert "K6_COORDINATOR_URL" in coordinator
    assert "/assignments/claim" in coordinator
    assert "/ready" in coordinator
    assert "/ws/lobby/rooms/" in lobby
    assert '"type":"ping"' in lobby.replace(" ", "")
    assert "/ws/match" in match
    assert "word.submit" in match
    assert "vote.submit" in match
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_assets.py::test_k6_flow_helpers_include_required_api_paths_and_ws_messages -q -o addopts=''
```

Expected: FAIL because flow helper files do not exist.

- [ ] **Step 3: Implement HTTP helper**

Create `k6/lib/http.js`:

```javascript
import { check, fail } from 'k6';

export function jsonHeaders(extra = {}) {
  return { headers: { 'Content-Type': 'application/json', ...extra } };
}

export function parseJson(response, label) {
  try {
    return response.json();
  } catch (error) {
    fail(`${label} returned non-JSON body status=${response.status}`);
  }
  return null;
}

export function expectStatus(response, expected, label) {
  const ok = check(response, {
    [`${label} status ${expected}`]: (res) => res.status === expected,
  });
  if (!ok) {
    fail(`${label} expected status=${expected} actual=${response.status} body=${response.body}`);
  }
}
```

- [ ] **Step 4: Implement auth and room helpers**

Create `k6/lib/auth.js` and `k6/lib/rooms.js` with these exported functions:

```javascript
// k6/lib/auth.js
import http from 'k6/http';
import { BASE_URL, PASSWORD, TEST_ID } from './config.js';
import { expectStatus, jsonHeaders, parseJson } from './http.js';

export function createAccount(vu, iteration) {
  const suffix = `${TEST_ID}_${vu}_${iteration}`.replace(/[^A-Za-z0-9_]/g, '_');
  return {
    account_id: `k6_${suffix}`.slice(0, 20),
    nickname: `k6_${vu}_${iteration}`.slice(0, 20),
    password: PASSWORD,
  };
}

export function signup(account) {
  const response = http.post(
    `${BASE_URL}/api/v1/auth/signup`,
    JSON.stringify(account),
    jsonHeaders(),
  );
  expectStatus(response, 201, 'signup');
  return parseJson(response, 'signup').data;
}

export function login(account) {
  const response = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ account_id: account.account_id, password: account.password }),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'login');
  return parseJson(response, 'login').data;
}
```

```javascript
// k6/lib/rooms.js
import http from 'k6/http';
import { BASE_URL, TEST_ID } from './config.js';
import { expectStatus, jsonHeaders, parseJson } from './http.js';

export function createRoom(roomSize, vu, iteration) {
  const response = http.post(
    `${BASE_URL}/api/v1/game/rooms`,
    JSON.stringify({
      name: `k6_${TEST_ID}_${roomSize}_${vu}_${iteration}`.slice(0, 50),
      game_type: 'word_chain',
      max_players: Math.max(roomSize, 1),
    }),
    jsonHeaders(),
  );
  expectStatus(response, 201, 'create room');
  return parseJson(response, 'create room').data;
}

export function joinRoom(roomPublicId) {
  const response = http.post(
    `${BASE_URL}/api/v1/game/rooms/${roomPublicId}/join`,
    null,
    jsonHeaders(),
  );
  expectStatus(response, 200, 'join room');
  return parseJson(response, 'join room').data;
}

export function startRoom(roomPublicId) {
  const response = http.post(
    `${BASE_URL}/api/v1/game/rooms/${roomPublicId}/start`,
    null,
    jsonHeaders(),
  );
  expectStatus(response, 200, 'start room');
  return parseJson(response, 'start room').data;
}
```

- [ ] **Step 5: Implement coordinator client**

Create `k6/lib/coordinator.js`:

```javascript
import http from 'k6/http';
import { sleep } from 'k6';
import { TEST_ID } from './config.js';
import { expectStatus, jsonHeaders, parseJson } from './http.js';
import { roomCoordinationFailures } from './metrics.js';

export const K6_COORDINATOR_URL = __ENV.K6_COORDINATOR_URL || 'http://127.0.0.1:8787';

export function claimAssignment(vu, iteration, roomSize = null) {
  const body = { test_id: TEST_ID, vu, iteration };
  if (roomSize) body.room_size = roomSize;
  const response = http.post(
    `${K6_COORDINATOR_URL}/assignments/claim`,
    JSON.stringify(body),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'claim assignment');
  return parseJson(response, 'claim assignment');
}

export function publishRoom(groupId, roomPublicId) {
  const response = http.post(
    `${K6_COORDINATOR_URL}/groups/${groupId}/room`,
    JSON.stringify({ room_public_id: roomPublicId }),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'publish room');
}

export function waitForRoom(groupId) {
  return waitForValue(`/groups/${groupId}/room`, 'room_public_id');
}

export function markReady(groupId, slotIndex) {
  const response = http.post(
    `${K6_COORDINATOR_URL}/groups/${groupId}/ready`,
    JSON.stringify({ slot_index: slotIndex }),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'mark ready');
}

export function waitForAllReady(groupId) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const response = http.get(`${K6_COORDINATOR_URL}/groups/${groupId}/ready`);
    expectStatus(response, 200, 'get ready');
    const payload = parseJson(response, 'get ready');
    if (payload.all_ready) return payload;
    sleep(0.2);
  }
  roomCoordinationFailures.add(1, { phase: 'ready' });
  return null;
}

export function publishSession(groupId, gameSessionPublicId) {
  const response = http.post(
    `${K6_COORDINATOR_URL}/groups/${groupId}/session`,
    JSON.stringify({ game_session_public_id: gameSessionPublicId }),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'publish session');
}

export function waitForSession(groupId) {
  return waitForValue(`/groups/${groupId}/session`, 'game_session_public_id');
}

function waitForValue(path, key) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const response = http.get(`${K6_COORDINATOR_URL}${path}`);
    if (response.status === 200) {
      const payload = parseJson(response, path);
      if (payload[key]) return payload[key];
    }
    sleep(0.2);
  }
  roomCoordinationFailures.add(1, { phase: key });
  return null;
}
```

- [ ] **Step 6: Implement WebSocket helpers**

Create `k6/lib/lobby-ws.js` and `k6/lib/match-ws.js`:

```javascript
// k6/lib/lobby-ws.js
import ws from 'k6/ws';
import { check } from 'k6';
import { BASE_WS_URL } from './config.js';
import { websocketConnectSuccess, websocketPingDuration } from './metrics.js';

export function connectLobby(roomPublicId) {
  const url = `${BASE_WS_URL}/ws/lobby/rooms/${roomPublicId}`;
  const started = Date.now();
  const result = ws.connect(url, {}, (socket) => {
    socket.on('open', () => {
      websocketConnectSuccess.add(true, { ws: 'lobby' });
      socket.send(JSON.stringify({ type: 'ping', payload: { client_time: String(Date.now()) } }));
    });
    socket.on('message', (raw) => {
      const message = JSON.parse(raw);
      if (message.type === 'lobby.pong') {
        websocketPingDuration.add(Date.now() - started, { ws: 'lobby' });
        socket.close();
      }
    });
  });
  check(result, { 'lobby ws status 101': (res) => res && res.status === 101 });
}
```

```javascript
// k6/lib/match-ws.js
import ws from 'k6/ws';
import { check } from 'k6';
import { BASE_WS_URL, MATCH_EVENT_WAIT_MS } from './config.js';
import {
  websocketConnectSuccess,
  wordSubmitAcceptedRate,
  wordSubmitAttempts,
  wordSubmitFailedRate,
  wordSubmitLatency,
  wordSubmitRejectedRate,
  wordSubmitTimeoutRate,
} from './metrics.js';
import { pickWordForTurn } from './word-pool.js';

export function connectMatchAndPlay({ gameSessionPublicId, seatNumber, wordPicker }) {
  const url = `${BASE_WS_URL}/ws/match?game_session_public_id=${gameSessionPublicId}`;
  let currentTurn = null;
  let submitStartedAt = 0;
  const result = ws.connect(url, {}, (socket) => {
    socket.on('open', () => websocketConnectSuccess.add(true, { ws: 'match' }));
    socket.on('message', (raw) => {
      const message = JSON.parse(raw);
      if (message.type === 'match.snapshot') {
        currentTurn = message.payload.current_turn;
        maybeSubmitWord(socket, currentTurn, seatNumber, wordPicker, () => {
          submitStartedAt = Date.now();
        });
      }
      if (message.type === 'match.turn.resolved') {
        recordWordResult(message.payload.result, Date.now() - submitStartedAt);
        currentTurn = message.payload.next_turn || null;
        maybeSubmitWord(socket, currentTurn, seatNumber, wordPicker, () => {
          submitStartedAt = Date.now();
        });
      }
      if (message.type === 'match.result.published') {
        socket.close();
      }
    });
    socket.setTimeout(() => socket.close(), MATCH_EVENT_WAIT_MS);
  });
  check(result, { 'match ws status 101': (res) => res && res.status === 101 });
}

function maybeSubmitWord(socket, turn, seatNumber, wordPicker, markStarted) {
  if (!turn || turn.actor_seat_number !== seatNumber) {
    return;
  }
  const candidate = pickWordForTurn(wordPicker, turn);
  if (!candidate) {
    return;
  }
  wordSubmitAttempts.add(1);
  markStarted();
  socket.send(JSON.stringify({
    type: 'word.submit',
    payload: { phase_id: turn.phase_id, word: candidate.normalized_word },
  }));
}

function recordWordResult(result, durationMs) {
  if (result === 'accepted') wordSubmitAcceptedRate.add(true);
  if (result === 'rejected') wordSubmitRejectedRate.add(true);
  if (result === 'timeout') wordSubmitTimeoutRate.add(true);
  if (result === 'failed') wordSubmitFailedRate.add(true);
  if (durationMs > 0) wordSubmitLatency.add(durationMs);
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_assets.py -q -o addopts=''
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add k6/lib/http.js k6/lib/auth.js k6/lib/rooms.js k6/lib/coordinator.js k6/lib/lobby-ws.js k6/lib/match-ws.js test/test_k6_assets.py
git commit -m "feat: add k6 e2e helpers"
```

## Task 6: Smoke Scenario

**Files:**
- Create: `k6/scenarios/smoke.js`
- Modify: `test/test_k6_assets.py`

- [ ] **Step 1: Write failing scenario asset test**

Append to `test/test_k6_assets.py`:

```python
def test_k6_smoke_scenario_runs_core_e2e_helpers() -> None:
    smoke = read("k6/scenarios/smoke.js")

    assert "createAccount" in smoke
    assert "signup" in smoke
    assert "createRoom" in smoke
    assert "claimAssignment" in smoke
    assert "waitForAllReady" in smoke
    assert "connectLobby" in smoke
    assert "startRoom" in smoke
    assert "connectMatchAndPlay" in smoke
    assert "smoke" in smoke
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_assets.py::test_k6_smoke_scenario_runs_core_e2e_helpers -q -o addopts=''
```

Expected: FAIL because `k6/scenarios/smoke.js` does not exist.

- [ ] **Step 3: Implement smoke scenario**

Create `k6/scenarios/smoke.js`:

```javascript
import { Trend } from 'k6/metrics';
import { createAccount, login, signup } from '../lib/auth.js';
import { createRoom, joinRoom, startRoom } from '../lib/rooms.js';
import {
  claimAssignment,
  markReady,
  publishRoom,
  publishSession,
  waitForAllReady,
  waitForRoom,
  waitForSession,
} from '../lib/coordinator.js';
import { connectLobby } from '../lib/lobby-ws.js';
import { connectMatchAndPlay } from '../lib/match-ws.js';
import { createWordPicker } from '../lib/word-pool.js';
import { e2eCycleDuration } from '../lib/metrics.js';

export const options = {
  scenarios: {
    smoke: {
      executor: 'constant-vus',
      vus: Number(__ENV.SMOKE_VUS || 1),
      duration: __ENV.SMOKE_DURATION || '1m',
    },
  },
  thresholds: {
    checks: ['rate>0.95'],
    http_req_failed: ['rate<0.05'],
  },
};

const smokeCycle = new Trend('smoke_cycle_duration', true);

export default function () {
  const started = Date.now();
  const assignment = claimAssignment(__VU, __ITER);
  const account = createAccount(__VU, __ITER);
  signup(account);
  login(account);

  let roomPublicId;
  if (assignment.is_owner) {
    const room = createRoom(assignment.room_size, __VU, __ITER);
    roomPublicId = room.room_public_id;
    publishRoom(assignment.group_id, roomPublicId);
  } else {
    roomPublicId = waitForRoom(assignment.group_id);
    joinRoom(roomPublicId);
  }

  connectLobby(roomPublicId);
  markReady(assignment.group_id, assignment.slot_index);

  let gameSessionPublicId;
  if (assignment.is_owner) {
    waitForAllReady(assignment.group_id);
    const session = startRoom(roomPublicId);
    gameSessionPublicId = session.game_session_public_id;
    publishSession(assignment.group_id, gameSessionPublicId);
  } else {
    gameSessionPublicId = waitForSession(assignment.group_id);
  }

  connectMatchAndPlay({
    gameSessionPublicId,
    seatNumber: assignment.slot_index + 1,
    wordPicker: createWordPicker(),
  });
  const duration = Date.now() - started;
  smokeCycle.add(duration);
  e2eCycleDuration.add(duration, { room_size: String(assignment.room_size) });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_assets.py -q -o addopts=''
```

Expected: PASS.

- [ ] **Step 5: Run live smoke when Docker stack is available**

Run after Task 1 compose stack is up and migrations/fixture are ready:

```bash
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS=p\(95\),p\(99\),min,max,avg \
TEST_ID=local-smoke-manual \
k6 run -o experimental-prometheus-rw --tag testid=local-smoke-manual k6/scenarios/smoke.js
```

Expected: k6 exits with status 0 and Prometheus contains `k6_` metrics tagged with `testid="local-smoke-manual"`.

- [ ] **Step 6: Commit**

```bash
git add k6/scenarios/smoke.js test/test_k6_assets.py
git commit -m "feat: add k6 smoke scenario"
```

## Task 7: Ramp and Soak Scenarios

**Files:**
- Create: `k6/scenarios/ramp-e2e.js`
- Create: `k6/scenarios/soak-e2e.js`
- Modify: `test/test_k6_assets.py`

- [ ] **Step 1: Write failing scenario tests**

Append to `test/test_k6_assets.py`:

```python
def test_k6_ramp_and_soak_scenarios_define_expected_load_patterns() -> None:
    ramp = read("k6/scenarios/ramp-e2e.js")
    soak = read("k6/scenarios/soak-e2e.js")

    assert "target: 10" in ramp
    assert "target: 50" in ramp
    assert "target: 100" in ramp
    assert "SOAK_VUS" in soak
    assert "SOAK_DURATION" in soak
    assert "connectMatchAndPlay" in ramp
    assert "connectMatchAndPlay" in soak
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_assets.py::test_k6_ramp_and_soak_scenarios_define_expected_load_patterns -q -o addopts=''
```

Expected: FAIL because ramp and soak files do not exist.

- [ ] **Step 3: Implement ramp scenario**

Create `k6/scenarios/ramp-e2e.js`:

```javascript
import smokeDefault from './smoke.js';

export const options = {
  scenarios: {
    ramp_e2e: {
      executor: 'ramping-vus',
      stages: [
        { duration: '1m', target: 10 },
        { duration: '3m', target: 10 },
        { duration: '1m', target: 50 },
        { duration: '5m', target: 50 },
        { duration: '1m', target: 100 },
        { duration: '5m', target: 100 },
        { duration: '1m', target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.10'],
    checks: ['rate>0.90'],
  },
};

export default smokeDefault;
```

- [ ] **Step 4: Implement soak scenario**

Create `k6/scenarios/soak-e2e.js`:

```javascript
import smokeDefault from './smoke.js';

export const options = {
  scenarios: {
    soak_e2e: {
      executor: 'constant-vus',
      vus: Number(__ENV.SOAK_VUS || 50),
      duration: __ENV.SOAK_DURATION || '30m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.10'],
    checks: ['rate>0.90'],
  },
};

export default smokeDefault;
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest test/test_k6_assets.py -q -o addopts=''
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add k6/scenarios/ramp-e2e.js k6/scenarios/soak-e2e.js test/test_k6_assets.py
git commit -m "feat: add k6 ramp and soak scenarios"
```

## Task 8: Documentation and Verification Commands

**Files:**
- Modify: `docs/load-testing/k6-be-load-test-plan.md`

- [ ] **Step 1: Add exact run commands to the load-test plan**

Append a `Run Commands` section to `docs/load-testing/k6-be-load-test-plan.md` with these commands:

````markdown
## Run Commands

Build and start the local load-test stack:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.load-test.yml \
  up -d --build postgres otel-collector prometheus tempo loki promtail grafana be-loadtest k6-coordinator
```

Generate the k6 word fixture:

```bash
.venv/bin/python scripts/generate_k6_word_fixture.py
```

Run smoke:

```bash
export TEST_ID=local-smoke-$(date +%Y%m%d%H%M%S)
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS=p\(95\),p\(99\),min,max,avg \
k6 run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/smoke.js
```

Run ramp:

```bash
export TEST_ID=local-ramp-$(date +%Y%m%d%H%M%S)
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS=p\(95\),p\(99\),min,max,avg \
k6 run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/ramp-e2e.js
```

Run 50 VU soak:

```bash
export TEST_ID=local-soak50-$(date +%Y%m%d%H%M%S)
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS=p\(95\),p\(99\),min,max,avg \
SOAK_VUS=50 \
SOAK_DURATION=30m \
k6 run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/soak-e2e.js
```

Run 100 VU soak:

```bash
export TEST_ID=local-soak100-$(date +%Y%m%d%H%M%S)
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS=p\(95\),p\(99\),min,max,avg \
SOAK_VUS=100 \
SOAK_DURATION=30m \
k6 run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/soak-e2e.js
```
````

- [ ] **Step 2: Run documentation placeholder scan**

Run:

```bash
rg -n "TB[D]|TO[D]O|FIXM[E]|[?][?]" docs/load-testing/k6-be-load-test-plan.md docs/superpowers/plans/2026-06-17-k6-be-load-test.md
```

Expected: no matches.

- [ ] **Step 3: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest test/test_load_test_compose.py test/test_k6_coordinator.py test/test_k6_word_fixture.py test/test_k6_assets.py -q -o addopts=''
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/load-testing/k6-be-load-test-plan.md docs/superpowers/plans/2026-06-17-k6-be-load-test.md
git commit -m "docs: add k6 load test implementation plan"
```

## Self-Review Checklist

- Spec coverage:
  - Docker BE/DB resource limits: Task 1.
  - Prometheus remote write: Task 1, Task 6, Task 8.
  - Valid word-chain submissions: Task 2, Task 3, Task 5, Task 6.
  - 1인 방 E2E: Task 6.
  - 2~4인 방 E2E: Task 4, Task 5, Task 6, Task 7.
  - Ramp and soak patterns: Task 7.
- Placeholder scan target: `rg -n "TB[D]|TO[D]O|FIXM[E]|[?][?]" docs/superpowers/plans/2026-06-17-k6-be-load-test.md`.
- Type/name consistency:
  - Fixture file is `k6/fixtures/word-pool.json`.
  - Word helper exports `createWordPicker` and `pickWordForTurn`.
  - Scenario files are `smoke.js`, `ramp-e2e.js`, `soak-e2e.js`.
