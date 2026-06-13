---
title: Agent Qdrant MVP
type: decision
updated: 2026-06-11
---

# Agent Qdrant MVP

## Decision

- Backend 게임 상태 처리는 Agent 범위에 포함하지 않는다.
- Backend의 `game_type`은 `shiritori`, `chosung`, `contains` handler 선택에만 사용하며
  Qdrant payload에는 `game_types`를 저장하지 않는다.
- handler는 `shiritori=start_word`, `chosung=chosung`, `contains=syllables` 조건으로
  Qdrant payload filter를 만든다.
- `used_words`는 Qdrant `word` 필드의 `must_not` 블랙리스트 조건으로 제외한다.
- 검증 완료 단어 payload는 `word`, `start_word`, `end_word`, `chosung`, `syllables`,
  `length`, `used_count`만 저장한다.
- Qdrant 후보가 있으면 `used_words`를 제외한 후보 중 최대 10개를 무작위 추출하고 그중 하나를
  무작위로 반환한다.
- Qdrant 후보가 없으면 game type별 프롬프트로 vLLM을 한 번 호출해 2~4글자 단어를 생성한다.
- 생성 결과는 `shiritori` 시작 글자, `chosung` 전체 초성, `contains` 포함 글자 조건과 길이,
  완성형 한글, `used_words` 중복 여부를 검증한다.
- 단어 적재와 답변 사용 횟수 증가는 FastAPI background task로 처리한다.
- request 멱등성은 MVP에서 프로세스 로컬 cache를 사용하고 Redis 교체 경계를 유지한다.
- Qdrant `used_count`는 read-modify-write이며 multi-pod 정합성 한계를 문서화한다.
- k3s에는 Agent, Qdrant StatefulSet/PV, vLLM 단일 GPU replica를 배포한다.
- 회사 cluster를 공개 Ingress로 직접 노출하지 않는다. Azure Nginx까지는 SSH reverse tunnel로
  NodePort `31080`을 전달한다.

## Consequences

- vLLM이 비활성화됐거나 호출/검증에 실패하면 `no_candidate`를 반환한다.
- 생성 단어는 Qdrant에 자동 적재하지 않으며 사용 횟수 갱신 대상에도 포함하지 않는다.
- 외부 사전 검증이 없으므로 생성 단어가 실제 사전에 등재된 단어인지 완전히 보장하지는 않는다.
- 동일 `request_id` 재시도는 한 프로세스 안에서 Qdrant/vLLM/count 중복 실행을 막는다.
- Pod 재시작이나 여러 Pod 간 완전한 멱등성 및 count 정합성은 Redis 도입 전까지 보장하지 않는다.
- Azure Nginx와 tunnel 관리는 k3s manifest와 분리된 운영 책임이다.
