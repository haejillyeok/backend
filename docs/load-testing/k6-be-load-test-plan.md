# k6 BE Load Test Plan

이 문서는 로컬 개발 환경에서 BE 서버를 대상으로 k6 부하테스트를 설계하고 실행하기 위한 1차 계획이다.
목표는 실제 게임 흐름에 가까운 E2E 부하를 만들고, 첫 실행에서는 통과/실패 판정보다 기준선을 수집하는 것이다.

## Goals

- 로컬 BE 서버를 `2 CPU / 4GB RAM`, PostgreSQL을 `1 CPU / 2GB RAM` 조건에서 실행한다.
- k6로 인증, 방 생성/참여, 로비 WebSocket, 게임 시작, 매치 WebSocket, 단어/투표 메시지까지 포함한 E2E 흐름을 테스트한다.
- 끝말잇기 규칙을 만족하는 유효 단어를 제출해 `word.submit` accepted 흐름을 측정한다.
- 1인 방뿐 아니라 2~4인 방 흐름도 포함한다.
- BE는 환경변수의 private IP Agent URL을 사용해 원격 Agent 서버를 실제 호출한다.
- k6 지표는 Prometheus remote write로 전송하고 Grafana에서 앱 지표와 함께 확인한다.
- 1차 실행은 SLO 판정이 아니라 p95/p99, 에러율, 처리량, WebSocket 연결 안정성, Agent 포함 지연 기준선을 수집한다.

## Non-Goals

- 운영 서버나 운영 DB를 대상으로 부하를 주지 않는다.
- 첫 계획 단계에서 테스트 데이터 cleanup을 필수로 만들지 않는다.
- 첫 실행 결과만으로 고정 SLO를 확정하지 않는다.
- BE 단독 성능과 Agent 포함 E2E 성능을 한 숫자로 단정하지 않는다.

## Target Environment

| Component | Plan |
| --- | --- |
| BE target | 로컬 Docker 컨테이너 |
| BE resource limit | `2 CPU / 4GB RAM` |
| DB target | 로컬 PostgreSQL 컨테이너 |
| DB resource limit | `1 CPU / 2GB RAM` |
| Agent target | 로컬 실행 아님. BE 환경변수의 private IP Agent URL로 원격 호출 |
| k6 target URL | 호스트 실행 시 `http://127.0.0.1:8000`, Docker network 실행 시 `http://be-loadtest:8000` |
| Observability | 기존 OpenTelemetry, Prometheus, Tempo, Loki, Grafana stack |

Agent는 원격 private IP 서버를 실제 호출한다. 따라서 결과에는 BE 처리 시간, DB 처리 시간, BE-to-Agent
네트워크 지연, Agent 처리 시간이 함께 섞인다. 결과를 볼 때 `audit.agent` 로그와 trace의 Agent client
span을 함께 확인해 Agent 포함 지연을 분리해서 해석한다.

## Docker Execution Model

기존 `docker-compose.yml`은 평소 개발 인프라용으로 유지한다. 부하테스트 전용 설정은 별도 override 파일에 둔다.

예상 파일:

- `docker-compose.load-test.yml`

예상 역할:

- `postgres`에 `cpus: "1.0"`, `mem_limit: 2g`를 적용한다.
- `be-loadtest` 서비스를 추가하고 `cpus: "2.0"`, `mem_limit: 4g`를 적용한다.
- `be-loadtest`는 루트 `Dockerfile`로 빌드한 image를 사용한다.
- `be-loadtest`는 `APP_MODULE=be`, `PORT=8000`, DB 환경변수, Agent 환경변수, OTEL 환경변수를 받는다.
- `prometheus`는 k6 remote write 수신을 위해 `--web.enable-remote-write-receiver`를 활성화한다.
- `k6-runner`는 호스트에 k6가 없는 로컬 환경에서도 Docker network 내부에서 k6를 실행할 수 있게 한다.
- 필요하면 k6 dashboard provisioning을 override에 추가한다.

예상 실행 흐름:

```bash
docker build -t haejillyeok-backend:loadtest .

docker compose \
  -f docker-compose.yml \
  -f docker-compose.load-test.yml \
  up -d postgres otel-collector prometheus tempo loki promtail grafana be-loadtest
```

DB migration은 BE 컨테이너 실행 전후 상태에 맞춰 명시적으로 적용한다. 현재 Docker runtime image에는 migration
tooling을 포함하지 않는 기준이 있으므로, 로컬 host의 개발 환경에서 다음 명령으로 실행하는 방식을 우선 검토한다.

```bash
mise run db-upgrade-head
```

단, load-test BE가 Docker network 안의 PostgreSQL을 바라보는 경우 host에서 migration을 수행할 때도 같은 DB에
접속하도록 `BE_DB_HOST`, `BE_DB_PORT` 값을 맞춘다.

## k6 Structure

k6 스크립트는 공통 helper와 실행 시나리오를 분리한다.

예상 파일:

- `k6/lib/auth.js`: 회원가입, 로그인, 쿠키 처리
- `k6/lib/rooms.js`: 방 목록, 방 생성, 방 참여, 방 나가기, 게임 시작
- `k6/lib/lobby-ws.js`: `/ws/lobby/rooms/{room_public_id}` 연결, 초기 이벤트 확인, ping
- `k6/lib/match-ws.js`: `/ws/match` 연결, snapshot 확인, ping, `word.submit`, `vote.submit`
- `k6/lib/word-pool.js`: `required_start_char`에 맞는 유효 끝말잇기 단어 선택
- `k6/fixtures/word-pool.js`: `scripts/valid_words_seed.sql`에서 생성한 k6용 valid word fixture
- `k6/lib/metrics.js`: custom Trend, Rate, Counter 정의
- `k6/lib/coordinator.js`: 2~4인 방 VU 조율 또는 사전 준비 데이터 사용
- `k6/scenarios/smoke.js`: 환경과 1인 방 기본 E2E 흐름 확인
- `k6/scenarios/ramp-e2e.js`: 10 -> 50 -> 100 VU 기준선 수집
- `k6/scenarios/soak-e2e.js`: 50 VU 30분 기본 soak, 100 VU 30분 확장 soak

## Scenario Mix

초기 방 규모 비율은 다음처럼 둔다.

| Room Size | Ratio | Purpose |
| --- | ---: | --- |
| 1 user + AI | 50% | 조율 실패가 적은 독립 E2E 기준선 |
| 2 users + AI | 20% | 최소 멀티플레이 방 흐름 |
| 3 users + AI | 15% | 중간 규모 로비/매치 broadcast |
| 4 users + AI | 15% | 현재 계획의 최대 실제 유저 방 규모 |

smoke는 빠른 검증을 위해 `K6_ROOM_SIZE=1`로 1인 방 전체 사이클을 먼저 확인한다. ramp/soak은 위 비율대로
1~4인 방을 섞어 실행한다. 2~4인 방은 여러 VU가 같은 방에 모여야 하므로 조율이 필요하다.

2~4인 방 기본 흐름:

1. 방장 VU가 회원가입 또는 로그인한다.
2. 방장 VU가 방을 만든다.
3. 참가자 VU가 회원가입 또는 로그인한다.
4. 참가자 VU들이 같은 `room_public_id`로 방에 참여한다.
5. 모든 실제 유저가 로비 WebSocket에 연결하고 `lobby.room.snapshot`을 확인한다.
6. 방장 VU가 게임 시작 API를 호출한다.
7. 각 유저가 `/ws/match`에 연결한다.
8. 현재 턴과 투표 단계에 맞춰 `ping`, 유효 끝말잇기 `word.submit`, `vote.submit`을 보낸다.
9. WebSocket 연결 종료와 REST leave는 1차에서는 필수 cleanup으로 보지 않는다.

## Load Patterns

### Smoke

목적: 실행 환경, DB 연결, Agent 연결, Prometheus remote write, 기본 E2E 흐름이 살아 있는지 빠르게 확인한다.

초기안:

- Duration: 1~2분
- VU: 1~5
- Room mix: 1인 방 위주, 2인 방 1개 포함
- 실패 시 ramp/soak를 진행하지 않는다.

### Ramp E2E

목적: 10 -> 50 -> 100 VU로 부하를 올리며 기준선을 수집한다.

초기안:

- 10 VU 유지: 3분
- 50 VU 유지: 5분
- 100 VU 유지: 5분
- 각 단계 사이 ramp-up/ramp-down: 1분
- Room mix: 1인 50%, 2인 20%, 3인 15%, 4인 15%

### Soak E2E

목적: 낮지 않은 부하를 오래 유지하며 DB connection, memory, WebSocket, Agent 호출 안정성을 확인한다.

기본:

- 50 VU / 30분
- Room mix: 1인 50%, 2인 20%, 3인 15%, 4인 15%

확장:

- 100 VU / 30분
- 기본 soak가 안정적일 때만 실행한다.

## Word Submission Strategy

끝말잇기 부하테스트는 서버가 거절할 단어를 무작위로 던지는 방식이 아니라, 가능한 한 실제 사용자가 정답 단어를
제출하는 흐름을 기본값으로 둔다. 서버는 `word.submit`을 처리할 때 현재 `phase_id`, 현재 턴 참가자,
deadline, `required_start_char`, `word_game.valid_words`, 현재 라운드의 `used_words`를 기준으로 검증한다.

### Valid Word Pool

k6는 테스트 전에 `word_game.valid_words`와 같은 기준의 단어 pool을 준비한다. 1차 구현에서는
`scripts/valid_words_seed.sql` 또는 DB에서 추출한 결과를 기반으로 `starts_with`별 단어 fixture를 만든다.

예상 fixture 형태:

```json
{
  "가": [
    {"word": "가구", "ends_with": "구"},
    {"word": "가방", "ends_with": "방"}
  ],
  "사": [
    {"word": "사과", "ends_with": "과"}
  ]
}
```

fixture 생성 기준:

- `game_type = "word_chain"`인 active 단어만 사용한다.
- `starts_with`를 key로 묶는다.
- `word`, `normalized_word`, `ends_with`를 보존한다.
- 한 실행 안에서 같은 라운드에 이미 사용한 단어는 다시 고르지 않는다.
- 후보가 없으면 무리하게 제출하지 않고 `word_pool_miss` custom metric을 올린다.

### Submit Timing and Turn Ownership

k6는 `/ws/match`의 `match.snapshot.current_turn` 또는 `match.turn.resolved.payload.next_turn`에서
`phase_id`, `actor_seat_number`, `required_start_char`, `started_at`, `deadline_at`을 읽는다.

- 현재 VU의 seat number가 `actor_seat_number`와 같을 때만 `word.submit`을 보낸다.
- `required_start_char`에 맞는 단어를 pool에서 고른다.
- `phase_id`는 현재 턴의 값을 그대로 사용한다.
- `deadline_at` 전에 제출한다. `started_at`이 미래이면 시작 시각까지 짧게 대기한 뒤 제출한다.
- 제출 후 `match.turn.resolved`를 기다려 `accepted`, `rejected`, `timeout`, `failed`를 기록한다.
- `accepted`면 `normalized_word`를 현재 라운드 used set에 추가하고, 다음 턴의 `required_start_char`로 이어간다.

1인 방 + AI에서는 사용자 턴과 AI 턴이 번갈아 올 수 있다. 사용자 VU는 자기 seat의 턴에서만 제출하고,
AI 턴에서는 BE가 원격 Agent를 호출해 이어지는 `match.turn.resolved` 이벤트를 기다린다.

2~4인 방에서는 각 참가자 VU가 자신의 match WebSocket에서 같은 broadcast event를 받는다. 각 VU는 자신의
seat number와 현재 `actor_seat_number`를 비교해 자기 차례일 때만 제출한다. 조율 저장소는 room 입장과
seat 배정에는 필요하지만, 단어 제출 차례 판단은 WebSocket event만으로 가능하게 설계한다.

### Metrics for Word Validity

단어 제출은 다음 custom metric으로 별도 기록한다.

- `word_submit_attempts`: `word.submit` 시도 수
- `word_submit_accepted_rate`: `match.turn.resolved.result = "accepted"` 비율
- `word_submit_rejected_rate`: `result = "rejected"` 비율
- `word_submit_reject_reason`: `word_start_char_mismatch`, `word_not_in_dictionary`, `word_already_used` 등 reason별 카운트
- `word_pool_miss`: `required_start_char`에 맞는 후보가 없어 제출하지 못한 횟수
- `word_submit_latency`: 제출 frame 전송부터 `match.turn.resolved` 수신까지의 시간
- `vote_submit_attempts`: `voting` 단계에서 `vote.submit`을 보낸 횟수
- `vote_submit_accepted_rate`: `match.vote.accepted` 수신 비율

첫 기준선에서는 accepted 흐름을 기본으로 하고, 일부러 틀린 단어를 보내는 negative test는 smoke나 별도
검증 시나리오로 분리한다.

## Metrics

### k6 Metrics

- HTTP 요청 수와 실패율
- REST API `http_req_duration` p95/p99
- 상태 코드별 실패
- WebSocket 연결 성공률
- WebSocket ping round-trip p95/p99
- `word.submit` accepted/rejected/timeout/failed 비율과 reject reason
- 방 규모별 E2E cycle duration
- 방 생성, 참가, 게임 시작, 매치 연결, 단어 제출, 투표 제출 단계별 custom Trend
- 2~4인 방 조율 실패율
- Agent 포함 게임 흐름의 전체 지연

### BE and Observability Metrics

- FastAPI throughput
- route별 p95/p99 latency
- 5xx error rate
- WebSocket active connections
- WebSocket message rate
- WebSocket error rate
- `audit.agent` 로그 기준 BE-to-Agent latency와 실패
- trace의 service, repository, Agent client span 지연
- BE 컨테이너 CPU/memory

### DB and Infrastructure Metrics

- PostgreSQL 컨테이너 CPU/memory
- DB connection pool 고갈 여부
- Prometheus remote write 수신 여부
- OTEL collector, Prometheus, Grafana 정상 수집 여부
- 로그 누락 또는 과도한 error log 증가 여부

## k6 Prometheus Remote Write

k6 지표는 Prometheus remote write output으로 전송한다. Grafana k6 공식 문서 기준으로 `experimental-prometheus-rw`
output은 remote write endpoint에 k6 time series를 전송하며, Prometheus에는 remote write receiver가 열려 있어야 한다.

참고 문서:

- [Grafana k6 Prometheus remote write](https://grafana.com/docs/k6/latest/results-output/real-time/prometheus-remote-write/)

예상 실행:

```bash
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS=p(95),p(99),min,max,avg \
k6 run -o experimental-prometheus-rw --tag testid=local-ramp-20260617-001 k6/scenarios/ramp-e2e.js
```

Docker network 내부에서 k6를 실행할 경우 `K6_PROMETHEUS_RW_SERVER_URL`은
`http://prometheus:9090/api/v1/write`를 사용한다.

호스트에 k6 CLI가 설치되어 있지 않으면 `docker-compose.load-test.yml`의 `k6-runner` 서비스를 사용한다.
이 경우 k6는 Docker network 안에서 `http://be-loadtest:8000`, `ws://be-loadtest:8000`,
`http://k6-coordinator:8787`, `http://prometheus:9090/api/v1/write`를 기본값으로 사용한다.

모든 실행에는 `testid` tag를 붙인다. 예시는 다음과 같다.

- `local-smoke-20260617-001`
- `local-ramp-20260617-001`
- `local-soak50-20260617-001`
- `local-soak100-20260617-001`

1차는 `K6_PROMETHEUS_RW_TREND_STATS=p(95),p(99),min,max,avg`를 사용한다. Prometheus native histogram은
설정 부담이 늘어나므로 2차 개선으로 검토한다.

## Data Policy

1차에서는 테스트 데이터 cleanup을 필수로 하지 않는다. 매 실행마다 고유 prefix를 붙인 계정과 방을 만들고 그대로 둔다.

권장 naming:

- `account_id`: `k6_<testid>_<vu>_<iteration>`
- `nickname`: `k6_<vu>_<iteration>`
- room name: `k6_<testid>_<room_size>_<vu>_<iteration>`

로컬 DB에 데이터가 많이 쌓여 기준선이 흔들리기 시작하면 다음 중 하나를 2차로 추가한다.

- cleanup script
- 별도 load-test DB
- 테스트 전 DB volume 초기화

## Multiplayer Coordination

2~4인 방은 k6 VU 간 동적 조율이 필요하다. k6의 `SharedArray`는 읽기 전용 데이터 공유에 적합하고,
실행 중 room id를 주고받는 rendezvous 저장소로 쓰기에는 맞지 않는다.

구현 단계에서 선택할 수 있는 방식:

1. setup 단계에서 계정과 방 배치를 미리 준비하고 VU가 정해진 slot을 소비한다.
2. 테스트 전용 coordinator API를 추가한다.
3. Redis 같은 외부 저장소를 coordinator로 사용한다.
4. 파일 기반 큐를 사용한다.

1차 권장안은 setup 단계에서 가능한 데이터를 최대한 준비하고, 부족한 동적 조율만 작은 coordinator로 처리하는 것이다.
테스트 전용 coordinator가 BE 제품 코드에 섞이지 않도록 k6 지원 도구나 별도 local-only 서비스로 분리한다.

조율 실패는 서버 장애로 오인하지 않도록 별도 custom metric으로 기록한다.

## Execution Checklist

1. Docker Desktop 또는 Docker runtime의 전체 리소스가 BE/DB 제한을 수용할 만큼 충분한지 확인한다.
2. `.env` 또는 shell 환경변수에 BE DB 설정과 Agent 설정이 들어 있는지 확인한다.
3. load-test image를 빌드한다.
4. `docker-compose.load-test.yml` override로 인프라와 `be-loadtest`를 실행한다.
5. migration을 적용한다.
6. `word_game.valid_words`에 `word_chain` active 단어가 적재됐는지 확인한다.
7. k6용 `starts_with`별 valid word fixture를 생성한다.
8. preflight로 필수 파일, word fixture, Agent URL, Docker/k6 실행 경로를 확인한다.
9. stack check로 `GET /health`, `GET /api/v1/health`, `GET /api/v1/agent/health`, Prometheus, coordinator를 확인한다.
10. Prometheus remote write receiver가 활성화됐는지 확인한다.
11. smoke를 실행한다.
12. smoke 실패가 없으면 ramp E2E를 실행한다.
13. ramp 결과에서 치명적 5xx, WebSocket close 급증, Agent 실패 급증이 없으면 50 VU soak를 실행한다.
14. 50 VU soak가 안정적이면 100 VU soak를 실행한다.
15. Grafana에서 `testid` 기준으로 k6 지표와 BE/DB/Agent 지표를 함께 확인한다.
16. 결과를 바탕으로 다음 실행의 SLO 후보를 정한다.

## Run Commands

Short mise task flow:

```bash
cp .env.load-test.example .env.load-test
# Edit .env.load-test and set AGENT_URL to the private IP Agent endpoint.
mise run load-test-up
mise run db-upgrade-head
mise run load-test-seed-valid-words
mise run load-test-db-word-check
mise run load-test-word-fixture
mise run load-test-preflight
mise run load-test-stack-check
export TEST_ID=local-smoke-$(date +%Y%m%d%H%M%S)
mise run load-test-smoke
mise run load-test-prometheus-check "$TEST_ID"
```

The `load-test-*` mise tasks use `.env.load-test` by default. To inspect or stop the stack:

```bash
mise run load-test-logs
mise run load-test-down
```

After a run, create a result note:

```bash
mise run load-test-result smoke "$TEST_ID"
```

Build and start the local load-test stack:

```bash
docker compose \
  --env-file .env.load-test \
  -f docker-compose.yml \
  -f docker-compose.load-test.yml \
  up -d --build postgres otel-collector prometheus tempo loki promtail grafana be-loadtest k6-coordinator
```

Generate the k6 word fixture:

```bash
.venv/bin/python scripts/generate_k6_word_fixture.py
```

생성 결과는 k6가 바로 import할 수 있는 `k6/fixtures/word-pool.js`이며, 각 항목은
`starts_with`별 `word`, `normalized_word`, `ends_with`를 포함한다. k6 시작 시간을 짧게 유지하기 위해
fixture는 기본적으로 시작 글자별 4개 단어만 포함한다. 필요하면 `--limit-per-start`로 조정한다.

Seed and verify valid words in the local DB:

```bash
docker compose \
  --env-file .env.load-test \
  -f docker-compose.yml \
  -f docker-compose.load-test.yml \
  exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < scripts/valid_words_seed.sql

.venv/bin/python scripts/k6_db_word_check.py --env-file .env.load-test
```

Run preflight before smoke:

```bash
.venv/bin/python scripts/k6_preflight.py
```

Run stack check after the compose stack starts:

```bash
.venv/bin/python scripts/k6_stack_check.py
```

Run with the Docker k6 wrapper:

아래 래퍼는 실행 전에 `scripts/k6_preflight.py`와 같은 preflight를 자동으로 수행하고, 실제 실행 시에는
`scripts/k6_stack_check.py`와 같은 stack check, `scripts/k6_db_word_check.py`와 같은 DB 단어 seed
확인까지 통과한 경우에만 Docker k6 runner를 실행한다.

```bash
.venv/bin/python scripts/run_k6_load_test.py smoke
.venv/bin/python scripts/run_k6_load_test.py ramp
.venv/bin/python scripts/run_k6_load_test.py soak50
.venv/bin/python scripts/run_k6_load_test.py soak100
```

`smoke` 래퍼는 기본적으로 `K6_ROOM_SIZE=1`을 전달하고, 기본 1회 E2E iteration만 실행한다.
반복 횟수를 늘려야 하면 `SMOKE_VUS`, `SMOKE_ITERATIONS`, `SMOKE_DURATION`을 조정한다. 2~4인 방 조율과
멀티플레이 부하는 `ramp`, `soak50`, `soak100`에서 확인한다.

명령만 확인하려면 `--dry-run`을 붙인다.

```bash
.venv/bin/python scripts/run_k6_load_test.py smoke --dry-run
```

If the load-test values are kept in `.env.load-test`, pass them explicitly:

```bash
.venv/bin/python scripts/k6_preflight.py --env-file .env.load-test
.venv/bin/python scripts/run_k6_load_test.py smoke --env-file .env.load-test
```

Check that k6 remote-write metrics arrived in Prometheus:

```bash
.venv/bin/python scripts/k6_prometheus_check.py "$TEST_ID"
```

The k6 assets and load-test helper scripts are verified by the load-test flow itself, not by
repository pytest. Keep the ordinary pytest suite focused on BE application behavior. Before a
load-test run, use `load-test-preflight`, `load-test-stack-check`, `load-test-db-word-check`, and
after the run use `load-test-prometheus-check` to catch broken local setup or missing k6 metrics.

Create a result note after a run:

```bash
.venv/bin/python scripts/k6_result_template.py smoke "$TEST_ID"
```

Run smoke:

```bash
export TEST_ID=local-smoke-$(date +%Y%m%d%H%M%S)
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS=p\(95\),p\(99\),min,max,avg \
k6 run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/smoke.js
```

Run smoke with Docker k6 runner:

```bash
export TEST_ID=local-smoke-$(date +%Y%m%d%H%M%S)
docker compose \
  -f docker-compose.yml \
  -f docker-compose.load-test.yml \
  run --rm \
  -e TEST_ID="$TEST_ID" \
  k6-runner run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/smoke.js
```

Run ramp:

```bash
export TEST_ID=local-ramp-$(date +%Y%m%d%H%M%S)
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS=p\(95\),p\(99\),min,max,avg \
k6 run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/ramp-e2e.js
```

Run ramp with Docker k6 runner:

```bash
export TEST_ID=local-ramp-$(date +%Y%m%d%H%M%S)
docker compose \
  -f docker-compose.yml \
  -f docker-compose.load-test.yml \
  run --rm \
  -e TEST_ID="$TEST_ID" \
  k6-runner run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/ramp-e2e.js
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

Run 50 VU soak with Docker k6 runner:

```bash
export TEST_ID=local-soak50-$(date +%Y%m%d%H%M%S)
docker compose \
  -f docker-compose.yml \
  -f docker-compose.load-test.yml \
  run --rm \
  -e TEST_ID="$TEST_ID" \
  -e SOAK_VUS=50 \
  -e SOAK_DURATION=30m \
  k6-runner run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/soak-e2e.js
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

Run 100 VU soak with Docker k6 runner:

```bash
export TEST_ID=local-soak100-$(date +%Y%m%d%H%M%S)
docker compose \
  -f docker-compose.yml \
  -f docker-compose.load-test.yml \
  run --rm \
  -e TEST_ID="$TEST_ID" \
  -e SOAK_VUS=100 \
  -e SOAK_DURATION=30m \
  k6-runner run -o experimental-prometheus-rw --tag testid="$TEST_ID" k6/scenarios/soak-e2e.js
```

## Risks

- 원격 Agent private IP 호출이 느리거나 실패하면 BE 성능과 구분해서 해석해야 한다.
- 2~4인 방 조율 실패가 실제 서버 장애처럼 보이지 않도록 custom metric을 분리해야 한다.
- 로컬 Docker Desktop 전체 리소스 제한이 실험 결과를 왜곡할 수 있다.
- Prometheus remote write receiver 설정이 빠지면 k6 지표가 보이지 않는다.
- 테스트 데이터 누적으로 DB query 성능이 장기적으로 달라질 수 있다.
- WebSocket timeout, grace leave, match timer가 테스트 duration과 겹치면 의도하지 않은 이벤트가 늘어날 수 있다.
- valid word fixture(`k6/fixtures/word-pool.js`)가 DB의 `word_game.valid_words`와 달라지면 제출 단어가 `word_not_in_dictionary`로 거절될 수 있다.
- 특정 시작 글자의 후보가 부족하면 `word_pool_miss`가 늘고 실제 게임 진행 부하가 낮아질 수 있다. smoke에서 이 값이 보이면 `--limit-per-start`를 늘려 fixture를 재생성한다.

## First Implementation Tasks

1. `docker-compose.load-test.yml`을 추가한다.
2. k6 디렉터리와 공통 helper 구조를 만든다.
3. valid word fixture 생성 절차와 `k6/lib/word-pool.js`를 구현한다.
4. smoke 시나리오를 먼저 구현한다.
5. 1인 방 E2E에서 실제 `required_start_char`에 맞는 단어 제출과 `accepted` 지표를 검증한다.
6. 2~4인 방 조율 방식을 결정하고 구현한다.
7. 2~4인 방에서 seat별 현재 턴 소유자가 `required_start_char`에 맞는 단어를 제출하는지 검증한다.
8. ramp E2E를 구현한다.
9. soak E2E를 구현한다.
10. k6 remote write 지표가 Prometheus/Grafana에서 조회되는지 확인한다.
11. 첫 기준선 실행 결과를 기록하고 SLO 후보를 별도 문서 또는 이 문서의 결과 섹션으로 갱신한다.
