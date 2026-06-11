---
title: LLM Wiki Maintenance
type: operating-guide
updated: 2026-06-11
audience: ai
---

# LLM Wiki Maintenance

`llm-wiki/`는 코드 변경 이력 저장소가 아니라 AI가 다음 작업에서 재사용할 프로젝트 지식 레이어다.
Git commit, PR, issue, 배포 기록에 남길 내용과 `llm-wiki/`에 남길 내용을 분리한다.

## What Belongs

위키에는 다음처럼 다음 작업자의 판단을 바꾸는 정보를 남긴다.

- 도메인 개념, 정책, 비즈니스 규칙
- public API, WebSocket message, DB schema 같은 외부/내부 계약
- 코드 컨벤션, 레이어 책임, 테스트 기준
- 운영/배포 기준 중 앞으로 따라야 할 현재 규칙
- 반복해서 참조할 아키텍처 결정과 그 이유
- 아직 확정되지 않은 질문과 확인해야 할 리스크

## What Does Not Belong

위키에는 다음 내용을 변경 이력처럼 누적하지 않는다.

- 특정 commit에서 어떤 파일을 추가, 삭제, 수정했는지에 대한 상세 목록
- README, workflow, Dockerfile, 테스트 파일 변경 자체에 대한 작업 보고
- 이미 코드나 Git history가 더 정확히 말하는 일회성 구현 과정
- 임시 디버깅 메모, 실행 로그, 로컬 환경에서만 의미 있는 산출물
- 현재 정책으로 압축되지 않은 과거 시도나 폐기된 구현 세부사항

코드 변경이 위키에 들어가야 하는 경우에는 “무엇을 바꿨다”가 아니라 “앞으로 어떤 기준을 따른다”로
정리한다.

## Log Scope

`llm-wiki/log.md`는 `llm-wiki/` 정보 자체의 변경 사항만 시간순으로 남긴다.

- 좋은 예: `runtime-configuration.md`에 Docker runtime과 배포 환경변수 기준을 통합했다.
- 좋은 예: `realtime-websocket.md`에 WebSocket envelope 계약과 문서 갱신 기준을 추가했다.
- 나쁜 예: `.github/workflows/docker-deploy.yml`에 input을 추가했다.
- 나쁜 예: `test/test_realtime_websocket.py` 테스트를 추가했다.

로그 항목은 위키 페이지, 개념, 결정, 계약, 운영 기준이 어떻게 바뀌었는지 1~3개 bullet로 요약한다.
코드 변경 세부사항이 필요하면 Git history를 본다.

## Page Hygiene

- 새 페이지는 `llm-wiki/index.md`에 링크와 1줄 요약을 추가한다.
- 확정된 기준은 현재형으로 쓰고, 구현 과정 설명은 제거한다.
- 오래된 기준은 삭제하거나 “대체됨”을 명시해 현재 기준과 충돌하지 않게 한다.
- 사람용 설명이 필요하면 `docs/`에 쓰되, AI 작업 기준은 `llm-wiki/`에 현재 정책으로 요약한다.
- 코드, 설정, 테스트가 최종 사실 기준이다. 위키와 충돌하면 위키를 고친다.

## Related

- [concepts/karpathy-llm-wiki.md](concepts/karpathy-llm-wiki.md)
- [decisions/2026-06-05-docs-vs-llm-wiki.md](decisions/2026-06-05-docs-vs-llm-wiki.md)
- [decisions/2026-06-05-llm-wiki-structure.md](decisions/2026-06-05-llm-wiki-structure.md)
