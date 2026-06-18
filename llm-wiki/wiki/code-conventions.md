---
title: Code Conventions
type: guide
updated: 2026-06-16
audience: ai
---

# Code Conventions

이 문서는 AI가 backend 코드를 작성하거나 수정할 때 따르는 코드 컨벤션이다. `docs/`는 사람 전용 문서이고, 이 파일이 AI 작업용 기준이다.

## Python

- Python 3.11 이상을 기준으로 작성한다.
- 타입 힌트를 기본으로 사용한다.
- collection 타입은 가능하면 `list[str]`, `dict[str, int]`처럼 built-in generic을 사용한다.
- 추상 collection은 `collections.abc`에서 import한다.
- 불필요한 약어보다 읽기 쉬운 이름을 우선한다.
- 파일명과 모듈명은 소문자 snake_case를 사용한다.
- 클래스명은 PascalCase, 함수/변수명은 snake_case, 상수는 UPPER_SNAKE_CASE를 사용한다.

## Imports

- 표준 라이브러리, 서드파티, 로컬 import 순서로 그룹화한다.
- 로컬 import는 `app...` absolute import를 기본으로 한다.
- 순환 import가 생기면 구조를 조정하고, 함수 내부 import로 숨기는 방식은 마지막 수단으로 둔다.

## Formatting

- Python 포맷은 `ruff`로 관리한다.
- 로컬 자동 정리는 `mise run format`을 사용한다.
- 변경 전 포맷 확인은 `mise run format-check`를 사용한다.
- 포맷 설정은 `pyproject.toml`의 `[tool.ruff]`를 기준으로 한다.

## Async

- I/O 작업은 async API를 우선한다.
- async 함수 안에서 blocking I/O를 직접 실행하지 않는다.
- background task가 필요하면 lifecycle, 취소, 예외 로깅, shutdown 방식을 함께 정의한다.
- 장기 실행 작업은 timeout/cancellation을 고려한다.

## Comments and Docstrings

- 로직 설명과 함수 docstring은 한국어로 작성한다.
- public 함수, service/repository 메서드, WebSocket connection manager 메서드는 의도, 주요 입력, 반환값, 부작용을 docstring 또는 가까운 주석으로 설명한다.
- 복잡한 분기, 비즈니스 규칙, timeout/cancellation 처리, transaction 경계, retry/compensation 로직에는 왜 그렇게 처리하는지 한국어 주석을 남긴다.
- 단순히 코드가 그대로 말하는 내용을 반복하는 주석은 쓰지 않는다.
- 주석은 구현 세부를 장황하게 풀기보다 유지보수자가 다음 수정 때 놓치면 안 되는 맥락을 남긴다.
- 외부 계약과 연결되는 함수는 관련 API, WebSocket message type을 주석이나 docstring에 명시한다.

## File Boundaries

- BE service 계층에서 핵심 service, connection manager, policy class는 파일당 하나를 기본으로 둔다.
- ORM 모델은 table/model class 하나를 파일 하나에 두는 것을 기본으로 하고, schema 상수는
  `constants.py`, public 호환 export는 package `__init__.py`에 둔다.
- Repository는 도메인 단위 class를 기본으로 유지한다. `GameRepository`, `MatchVoteRepository`처럼
  도메인 repository 하나가 그 도메인의 DB 실행 함수를 소유한다.
- Repository 메서드 하나는 조회 1회, row 추가 1건, flush/commit 1회, 상태 row 1건 변경처럼 하나의
  DB 실행 책임만 담당한다. 여러 조회/변경을 순서대로 조합하는 비즈니스 플로우는 service/usecase에 둔다.
- API endpoint 모듈이 커지면 기존 router import 경로는 package facade로 유지하고, room/session/entry처럼
  REST 자원 또는 유스케이스별 router 모듈로 분리한다.
- WebSocket endpoint 모듈이 커지면 기존 router import 경로는 package facade로 유지하고, 연결 인증,
  message loop, timeout/grace 처리처럼 lifecycle 책임별 모듈로 분리한다.
- 문서/HTML을 반환하는 endpoint가 커지면 route 함수와 Markdown/HTML renderer를 분리해 route는
  파일 읽기와 HTTP 변환만 담당하게 둔다.
- 작은 dataclass DTO, snapshot, event payload, timer record는 `records.py`, `snapshots.py`,
  `events.py`, `timers.py`처럼 역할별 파일에 묶을 수 있다.
- 기존 public import 경로가 넓게 쓰이는 모듈을 패키지로 나눌 때는 `__init__.py`에서 기존 이름을
  re-export해 endpoint, repository, test의 import churn을 줄인다.
- 게임 규칙, 참가자 생성, 토큰 발급, 점수/투표/턴 판단처럼 바뀔 수 있는 정책은 service 내부 분기보다
  주입 가능한 policy 객체로 분리한다.
- policy 객체는 가능한 한 DB와 WebSocket에 직접 의존하지 않는 순수 규칙으로 두고, service가 repository,
  client, manager와 조합한다.

## Layering

### API Endpoint

- HTTP/WebSocket 프로토콜 처리와 dependency wiring을 담당한다.
- request/response schema 변환을 담당한다.
- 비즈니스 규칙을 길게 담지 않는다.
- DB session, repository 생성, transaction rollback/commit을 직접 다루지 않는다. WebSocket controller도
  연결 수명이 길어질 수 있으므로 인증/권한 확인용 DB transaction을 붙잡지 않는다.

### Service

- 유스케이스와 비즈니스 규칙을 담당한다.
- repository, client wrapper, domain helper를 조합한다.
- FastAPI `Request`, `Response`, `WebSocket` 객체에 직접 의존하지 않는다.
- 여러 repository DB 실행 함수를 순서대로 호출하는 transaction 흐름은 service/usecase가 담당한다.
  service는 app sessionmaker로 만든 repository context factory를 받아 usecase 진입점에서 짧은
  repository scope를 열고 닫는다.
- 외부 HTTP/API 호출은 DB transaction 밖에서 실행한다. 필요한 DB context는 먼저 조회 transaction으로
  snapshot화하고 닫은 뒤 외부 호출을 수행하며, 외부 호출 결과를 반영할 때 새 transaction을 연다.
- 같은 transaction에서 새 row의 기본키를 다른 row의 외래키로 사용하면, 부모 row를 먼저 추가하고
  `flush()`로 DB 제약과 식별자를 확정한 뒤 자식 row를 추가한다. SQLAlchemy flush ordering이나
  애플리케이션 생성 UUID에 의존해 순서를 숨기지 않는다.
- 게임 정책, 검증 정책, 점수 계산 정책은 주입 가능한 policy 객체/함수로 받아 service/usecase에서 호출한다.

### Repository

- DB 접근을 담당한다.
- SQLAlchemy session은 dependency에서 받아온다.
- API schema를 직접 반환하지 않고 persistence model 또는 domain data를 반환한다.
- Repository 메서드는 쿼리 실행과 DB row/list 반환에 집중한다. 조회 결과가 없거나 조건에 맞지 않는
  경우에도 `AppException`/`ErrorCode`로 변환하지 않고 `None`이나 빈 목록 같은 DB 조회 결과를 그대로
  반환한다.
- 여러 조회 결과를 조합해 application DTO를 만들거나, row 값의 의미를 판단해 흐름을 나누는 작업은
  service/usecase 책임이다.
- 비즈니스 플로우, 게임 정책 판단, WebSocket broadcast payload 조립을 담당하지 않는다.

### Schemas

- request schema는 `schemas/request/`에 둔다.
- response schema는 `schemas/response/`에 둔다.
- 여러 계층에서 공유되는 base model은 `schemas/base.py`에 둔다.

### Shared

- `app/shared/`에는 두 서버가 정말 공유하는 설정, logging, client wrapper만 둔다.
- 특정 서버의 도메인 로직을 `shared`로 옮기지 않는다.

## Error Conventions

- domain/service 계층은 HTTPException에 직접 의존하지 않는다.
- endpoint는 domain exception을 HTTP status로 변환한다.
- 로그에는 내부 원인을 남기되, 외부 response에는 필요한 정보만 노출한다.

## API Conventions

- REST API는 `/api/v1` prefix를 사용한다.
- health check는 root-level `/health`와 versioned `/api/v1/health`를 유지한다.
- 새 endpoint는 response model과 status code를 명시한다.
- public API 변경은 AI 작업 기준으로 `llm-wiki/`에 기록하고, 사람이 읽는 설명이 필요하면 `docs/api.md`에도 반영한다.

## Client Wrapper Conventions

- 서버 간 호출은 기능별 wrapper를 통해 수행하고 timeout을 명시한다.
- client wrapper는 외부 응답을 service 계층이 쓰기 쉬운 domain data로 매핑한다.
- retry가 필요하면 멱등성과 timeout budget을 먼저 확인한다.

## WebSocket Conventions

- WebSocket 메시지는 JSON envelope를 사용한다.
- envelope에는 최소 `type`, `payload`를 둔다.
- 추적이 필요한 메시지는 `request_id`, 순서가 중요한 메시지는 `sequence`를 둔다.
- connection manager는 endpoint 함수에서 분리한다.
- disconnect cleanup은 테스트한다.

## Tests

- 테스트 파일은 `test/` 아래에 둔다.
- `pytest`는 전체 `app` package coverage를 측정하고 총 coverage 90% 이상을 유지한다.
- 새 public API는 정상 응답과 주요 실패 응답을 테스트한다.
- dependency override가 필요한 테스트는 `create_app()`으로 앱을 생성한다.
- client wrapper는 timeout, status handling, mapping을 테스트한다.
- WebSocket은 연결, 메시지 송수신, disconnect cleanup을 테스트한다.
- k6 부하테스트 자산과 load-test helper script는 일반 pytest suite에 포함하지 않는다.
  `load-test-preflight`, `load-test-stack-check`, `load-test-db-word-check`, 실제 k6 run,
  `load-test-prometheus-check`로 실행 전후 상태를 검증한다.
- Grafana dashboard JSON은 일반 pytest suite에 포함하지 않는다. Dashboard 변경은 Grafana provisioning,
  datasource query, 실제 화면 또는 API 확인으로 검증한다.

## Git Commit Messages

- 커밋 메시지는 `<type>: <english summary>` 형식의 한 줄 영어 문장으로 작성한다.
- 허용 type은 `feat`, `fix`, `refactor`, `chore`, `test`, `ci`, `docs`를 기본으로 한다.
- summary는 imperative mood를 사용하고 첫 단어는 소문자로 시작한다.
- summary 끝에는 마침표를 붙이지 않는다.
- 기본 형식에는 scope를 넣지 않는다.

```text
feat: add realtime websocket endpoint
fix: handle file logging setup errors
refactor: simplify docker app module selection
chore: update runtime configuration defaults
test: add websocket validation coverage
ci: add manual database migration workflow
docs: clarify llm wiki maintenance policy
```

## Documentation

- 사람이 읽는 문서는 `docs/`에 남긴다.
- AI가 작업할 때 사용할 수 있는 모든 정보는 `llm-wiki/`에 남긴다.
- 코드 컨벤션, 프레임워크 가이드라인, 결정 기록은 `docs/`에만 두지 말고 `llm-wiki/`에도 유지한다.
