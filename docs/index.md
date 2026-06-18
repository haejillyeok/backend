# Documentation Index

이 디렉터리는 사람이 보는 프로젝트 문서입니다.

## Project Docs

- [Architecture](architecture.md): 서버 구조와 모듈 경계
- [API](api.md): REST API 계약
- [Sunset Domain](sunset-domain.md): 해질녘 게임 도메인, 상태 흐름, WebSocket 진행 기준
- [Development](development.md): 개발 환경, DB, 실행, 테스트 절차
- [k6 BE Load Test Plan](load-testing/k6-be-load-test-plan.md): 로컬 BE E2E 부하테스트 계획, Docker 리소스 제한, k6/Grafana 관측 기준
- [Backend Guidelines](backend-guidelines.md): FastAPI, WebSocket 적용 기준
- [Code Conventions](code-conventions.md): Python 코드 스타일, 레이어 규칙, 테스트 기준

## Docs vs LLM Wiki

- `docs/`: 사람이 읽는 문서
- `llm-wiki/`: AI가 작업할 때 사용하는 지식, 코드 컨벤션, 가이드라인, 결정 기록

AI가 작업에 사용할 수 있는 모든 정보는 `llm-wiki/`에 있어야 합니다. `docs/`에만 있는 내용이 AI 작업에도 필요하면 `llm-wiki/`에도 정리합니다.
