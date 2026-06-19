# ADR Index

구조적 결정은 이 폴더에 ADR로 남긴다. ADR은 사람이 함께 읽는 의사결정 보고서이며,
선택지, trade-off, 영향, 검증 방법을 보존한다. 확정된 현재 기준은 필요 시 `llm-wiki/`에 요약한다.

Codex는 작업 시작과 설계 중 ADR 필요 여부를 먼저 판단한다. 사용자가 별도로 요청하지 않아도
public API, WebSocket 계약, DB schema, 모듈 경계, 배포/운영 기준, 되돌리기 어려운 기술 선택처럼
다음 작업자의 판단을 바꾸는 결정은 ADR로 남긴다.

## Immutability

- `proposed` ADR은 논의 중이므로 내용 수정이 가능하다.
- `accepted` ADR은 결정의 역사로 보존하며 의미를 바꾸는 수정을 하지 않는다.
- `accepted` ADR에는 오타, 링크, 관련 PR, 관련 위키 같은 비의미적 정정만 반영한다.
- 결정, 근거, trade-off, consequence가 바뀌면 기존 ADR을 고치지 않고 새 ADR을 만든다.
- 새 ADR은 `Supersedes`로 기존 ADR을 참조하고, 기존 ADR은 `Superseded by`만 갱신한다.

## Records

- [2026-06-19 Auth Input Rules](2026-06-19-auth-input-rules.md)

## Template

- [template.md](template.md)
