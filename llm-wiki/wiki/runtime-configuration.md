---
title: Runtime Configuration
type: guide
updated: 2026-06-09
audience: ai
---

# Runtime Configuration

서버 프로세스가 직접 읽는 런타임 값은 `.env`와 OS 환경변수로 제어한다. OS 환경변수가
`.env`보다 우선하며, 값이 없으면 로컬 기본값을 쓴다. Docker Compose 인프라 host port는
서버 `.env` 관리 대상에 넣지 않는다.

## App Servers

`app/shared/core/config/http.py`는 앱 이름에서 서비스 prefix를 만든 뒤 서버 HTTP 포트 값을 읽는다.
HTTP host는 `127.0.0.1`로 고정한다.

| Server | HTTP default |
| --- | --- |
| `haejillyeok-be` | `127.0.0.1:8000` |
| `haejillyeok-agent` | `127.0.0.1:8001` |

`mise run dev-be`와 `mise run dev-agent`는 HTTP port 값을 uvicorn에 넘긴다. FastAPI
lifespan에서 gRPC 서버를 함께 시작하지 않는다.

## Observability

서버의 APM exporter 연결은 `.env`의 활성화 값으로 제어한다. 기본값은 활성화다.
특정 상황에서 관측 전송을 끄고 싶을 때만 값을 비활성화한다. Collector가 기본 포트가 아닌
곳에 있으면 exporter endpoint 값을 실제 Collector endpoint로 맞춘다.

## Container Build Context

공개 Docker image를 만들 때 로컬 secret과 작업 상태를 build context에 포함하지 않는다.
루트 `.dockerignore`는 `.env`, `.env.*`, Git/도구 캐시, 가상환경, 테스트/coverage/build 산출물,
runtime artifact, Python bytecode/cache, migration tooling, 로컬 editor 파일, 사람용 문서와 AI용
`llm-wiki/`, 테스트 코드를 제외한다.
운영 secret은 image에 bake하지 않고 컨테이너 실행 환경에서 환경변수나 배포 platform secret으로
주입한다.

## Container Runtime

루트 `Dockerfile`은 `python:3.11-slim` 기반 단일 runtime image를 만든다. 기본 실행 대상은
`APP_MODULE=be`, `PORT=8000`이며, 같은 image에서 agent를 실행해야 하면
컨테이너 실행 환경에 `APP_MODULE=agent`, `PORT=8001`을 주입한다. Uvicorn 실행 대상은
`app.${APP_MODULE}.main:app` 형태로 조립한다. Uvicorn은
컨테이너 외부 port publishing이 가능하도록 `HOST=0.0.0.0`을 기본값으로 사용한다. worker 수는
`WORKERS` 환경변수로 제어하며 기본값은 `1`이다. `docker run`에서는 같은 shell `PORT` 값을
`-e PORT="$PORT"`와 `-p "$PORT:$PORT"`에 함께 넘겨 host port와 container port를 동일하게
맞춘다.

Docker Hub에 올릴 때는 로컬 이미지명 `haejillyeok-backend`가 아니라
`your-dockerhub-username/haejillyeok-backend:0.1.0`처럼 Docker Hub 계정명 기반 tag를 붙인다. 단일 플랫폼 빌드는
`docker build` 후 `docker push`를 사용하고, Mac에서 빌드해 Linux 서버나 여러 CPU 아키텍처에서
실행할 image는 `docker buildx build --platform linux/amd64,linux/arm64 --push`를 사용한다.
Runtime image에는 `alembic.ini`와 `migrations/`를 포함하지 않는다. DB migration은 앱 컨테이너
실행 전 별도 배포 단계에서 실행한다.

Docker run 시 `.env`는 image에 포함되지 않으므로 필요한 값을 컨테이너 실행 환경에서 주입한다.
`be` 서버는 `BE_ENV`, `BE_DB_HOST`, `BE_DB_PORT`, `BE_DB_USER`, `BE_DB_PASSWORD`, `BE_DB_NAME`이
필수다. `agent` 서버는 DB 환경변수를 사용하지 않지만 shared app/observability 설정을 위해
`BE_ENV`, `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_METRIC_EXPORT_INTERVAL`을 실행
환경에서 명시한다. Collector를 쓰지 않는 배포에서는 `OTEL_ENABLED=false`로 둔다.
