---
title: Runtime Configuration
type: guide
updated: 2026-06-10
audience: ai
---

# Runtime Configuration

서버 프로세스가 직접 읽는 런타임 값은 `.env`와 OS 환경변수로 제어한다. OS 환경변수가
`.env`보다 우선하며, 값이 없으면 로컬 기본값을 쓴다. Docker Compose 인프라 host port는
서버 `.env` 관리 대상에 넣지 않는다.

## App Servers

`app/shared/core/config/app.py`는 공통 앱 설정을 읽는다. 서버 프로세스의 기본 타임존은
KST(`Asia/Seoul`)이며, `APP_TIMEZONE` 환경변수로 명시한다. 값이 없으면 코드 기본값
`Asia/Seoul`을 사용한다. 앱 시작 시 이 값을 `TZ` 환경변수와 C runtime timezone 상태에 적용하므로
logging formatter의 로컬 시각도 KST를 따른다. DB 저장/비교용 timestamp와 public API/WebSocket
payload의 서버 생성 timestamp도 KST timezone-aware datetime을 기준으로 한다.

`app/shared/core/config/http.py`는 앱 이름에서 서비스 prefix를 만든 뒤 서버 HTTP 포트 값을 읽는다.
HTTP host는 `127.0.0.1`로 고정한다.

| Server | HTTP default |
| --- | --- |
| `haejillyeok-be` | `127.0.0.1:8000` |
| `haejillyeok-agent` | `127.0.0.1:8001` |

`mise run dev-be`와 `mise run dev-agent`는 HTTP port 값을 uvicorn에 넘긴다. FastAPI
lifespan에서 gRPC 서버를 함께 시작하지 않는다.

## CORS

`app/shared/core/cors.py`는 브라우저에서 직접 호출되는 `be` 서버의 CORS middleware 설정을 둔다.
현재 `be` 허용 origin은 `http://localhost:3000`, `https://haejillyeok.com`,
`https://agent.haejillyeok.com`, `https://www.haejillyeok.com`이다. method/header는 모두
허용하고, 세션 쿠키 기반 API 요청을 막지 않도록 `allow_credentials=True`도 함께 둔다.
`agent` 서버는 `be`에서 서버 간 HTTP로 호출하므로 CORS middleware를 등록하지 않는다. agent 접근
범위 제한은 CORS가 아니라 네트워크 ACL, 방화벽, 서비스 인증 같은 서버 측 제어로 다룬다.

## Observability

서버의 APM exporter 연결은 `.env`의 활성화 값으로 제어한다. 기본값은 활성화다.
특정 상황에서 관측 전송을 끄고 싶을 때만 값을 비활성화한다. Collector가 기본 포트가 아닌
곳에 있으면 exporter endpoint 값을 실제 Collector endpoint로 맞춘다.
`OTEL_EXPORTER_OTLP_ENDPOINT`는 `http://localhost:4318` 같은 OTLP HTTP base endpoint로 둔다.
앱은 metric exporter에는 `/v1/metrics`, trace exporter에는 `/v1/traces`를 붙여 전송한다.

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
`be` 서버는 `BE_ENV`, `APP_TIMEZONE`, `BE_DB_HOST`, `BE_DB_PORT`, `BE_DB_USER`, `BE_DB_PASSWORD`,
`BE_DB_NAME`이 필수다. `agent` 서버는 DB 환경변수를 사용하지 않지만 shared app/observability
설정을 위해 `BE_ENV`, `APP_TIMEZONE`, `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_METRIC_EXPORT_INTERVAL`을 실행 환경에서 명시한다. `APP_TIMEZONE`은 기본적으로
`Asia/Seoul`을 사용한다. OpenTelemetry 기본값은 `OTEL_ENABLED=true`이며, Collector를 쓰지 않는
배포에서만 `false`로 끈다. Collector와 같은 Docker network에서 실행하는 배포는
`OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`을 사용한다.

## Agent Runtime

Agent는 `QDRANT_URL=http://qdrant:6333`, `QDRANT_COLLECTION=game_words`,
`VLLM_BASE_URL=http://vllm:8000`, `VLLM_MODEL_NAME=shiritori-llm`을 기본값으로 사용한다.
`USE_VLLM=false`, `USE_REDIS_COUNTER=false`가 MVP 기본값이다. 비즈니스 API는 최소 32자의
`AGENT_API_KEY`가 없으면 fail closed하며, k3s에서는 `agent-api-auth` Secret의 `api-key`에서
주입한다.

`deploy/k3s/agent-service.yaml`은 회사 내부 control-plane의 NodePort `31080`을 유지한다.
공개 도메인/TLS를 회사 k3s Ingress가 직접 소유하지 않는다. 현재 운영 경로는 회사 서버가
Azure VM의 `127.0.0.1:31080`으로 여는 SSH reverse tunnel과 Azure Nginx이다. 따라서
`deploy/k3s/kustomization.yaml`에 공개 Agent Ingress나 TLS Secret을 포함하지 않는다.

vLLM은 `vllm/vllm-openai:v0.22.1` 단일 replica이며 `enableServiceLinks=false`로 Kubernetes가
주입하는 `VLLM_PORT=tcp://...`와 vLLM 자체 환경변수 이름 충돌을 막는다. 모델은 GPU node의
`/home/goodsee/llm_model/model/MODEL/Qwen3.5-9B`를 Pod
`/models/Qwen3.5-9B`에 read-only hostPath로 mount한다.

## BE to Agent Runtime

BE에서 Agent 서버를 호출할 때는 `app/shared/clients/agent.py`의 전용 HTTP client wrapper를
사용한다. BE의 public `/api/v1/agent/health`는 배포 환경에서 주입한 Agent base URL과 공유
secret으로 Agent `/api/v1/health`를 호출한다. Agent health API 자체는 인증을 강제하지 않더라도
BE client는 비즈니스 API와 같은 인증 header를 항상 보낸다.

배포 workflow에는 Agent 연결 정보 기본값을 두지 않는다. 실제 운영 네트워크에서 BE가 접근할 수
있는 Agent base URL과 Agent k3s Secret `agent-api-auth`의 `api-key`와 같은 공유 secret을 GitHub
Secrets로 주입해야 한다.

## GitHub Actions Deployment

`.github/workflows/docker-deploy.yml`은 `workflow_dispatch`만 사용한다. 수동 실행 input
`confirm_deploy`가 `deploy`일 때만 Docker Hub build/push와 SSH 배포를 실행하고, `no`이면 확인
job만 실행한다. 확인 job은 최근 Git tag 목록을 출력하므로 배포 전 태그 조회용으로도 사용할 수
있다.

GitHub runner는 수동 실행 input `target_tag`를 Docker image tag로 사용한다. 배포 job은
`target_tag`가 비어 있거나, 실제 Git tag가 아니거나, commit을 가리키지 않거나, Docker image tag
형식에 맞지 않으면 실패한다. 유효한 tag이면 해당 tag ref를 checkout한 뒤 Docker Hub에는
`DOCKERHUB_USERNAME/haejillyeok-backend:{version-tag}`와 `latest` tag를 함께 push한다. 원격
서버에는 `deploy` 계정으로 SSH 접속하고, `/opt/haejillyeok/backend/.env` 파일을 생성한 뒤
`docker run --env-file`로 컨테이너 환경변수에 주입한다. 원격 `.env`는 `deploy`만 읽을 수 있도록
`600` 권한을 유지한다. `deploy` 계정은 `/opt/haejillyeok/backend`에 쓸 수 있어야 한다. 파일
로그는 원격 서버의 `/var/log/haejillyeok/*.log*`에 보존한다. Workflow는
`/var/log/haejillyeok`를 컨테이너 `/app/logs`로 bind mount하고, 배포 image를 root로 한 번
실행해 host 로그 디렉터리 소유권을 컨테이너의 `app` 사용자에 맞춘 뒤 실제 컨테이너를 실행한다.
원격 컨테이너는
기본적으로 `APP_MODULE=be`, `PORT=8000`으로 실행하고 `DOCKER_NETWORK`에 지정한 user-defined
Docker network에 붙인다. Workflow가 생성하는 `.env`에는 `BE_ENV=prod`,
`APP_TIMEZONE=Asia/Seoul`, `LOG_DIR=/app/logs`를 고정으로 쓴다. 원격 서버에는 Docker Hub
credential을 전달하지 않고 public image를 pull한다.

필수 GitHub Secrets는 `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `DEPLOY_HOST`, `DEPLOY_SSH_KEY`,
`BE_DB_HOST`, `BE_DB_USER`, `BE_DB_PASSWORD`, `BE_DB_NAME`과 Agent 연결 secrets이다. 선택 GitHub Variables는
`DEPLOY_SSH_PORT`, `DOCKER_NETWORK`, `BE_DB_PORT`, `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_METRIC_EXPORT_INTERVAL`, `LOG_FILE_ENABLED`, `LOG_RETENTION_DAYS`, `LOG_MAX_TOTAL_BYTES`,
`LOG_CLEANUP_INTERVAL_SECONDS`이다. `DOCKER_NETWORK` 기본값은 `backend_default`이고,
`OTEL_EXPORTER_OTLP_ENDPOINT` 기본값은 `http://otel-collector:4318`이다. Workflow가 생성하는
`.env`의 `BE_ENV`는 항상 `prod`, `APP_TIMEZONE`은 항상 `Asia/Seoul`로 고정한다.

## GitHub Actions DB Migration

`.github/workflows/db-migration.yml`은 `workflow_dispatch` 전용 운영 DB 작업 workflow다. Docker
runtime image에는 migration tooling을 넣지 않으므로 GitHub runner가 레포를 checkout하고 `mise`로
개발 의존성을 설치한 뒤 Alembic을 실행한다.

Private subnet DB는 GitHub runner가 직접 접근하지 않는다. Workflow는 `DEPLOY_HOST`에 `deploy`
계정으로 SSH 접속해 로컬 포워딩을 열고, Alembic 실행 환경에는 `BE_DB_HOST=127.0.0.1`,
`BE_DB_PORT=15432`를 주입한다. 실제 private DB endpoint는 `BE_DB_HOST` secret에 둔다. 이 값은
deploy 인스턴스에서 접근 가능한 주소여야 한다.

실행 input `db_task`는 로컬 `mise` DB task 이름과 맞춘다. 기본값은 `db-upgrade-head`이고,
`db-current`, `db-history`, `db-upgrade`, `db-downgrade`, `db-downgrade-one`을 선택할 수 있다.
`db-upgrade`와 `db-downgrade`는 `target_revision` input을 함께 요구한다. 운영 DB 변경은
`confirm_action=run`일 때만 실행되며, workflow concurrency group `prod-db-migration`으로 동시에
두 migration job이 실행되지 않게 한다.
