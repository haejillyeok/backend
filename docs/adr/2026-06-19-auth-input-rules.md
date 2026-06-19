# ADR: Auth Input Rules

- Date: 2026-06-19
- Status: accepted
- Context: 회원가입 화면은 계정, 비밀번호, 닉네임 입력 제약을 명확히 보여준다. Backend public API validation도 같은 제약을 가져야 프론트와 서버가 같은 실패 조건을 사용자에게 보여줄 수 있다.

## Decision

- `account_id`는 영어 문자, 숫자, `_`만 허용하고 3~20자로 제한한다.
- `password`는 공백 없는 ASCII 문자, 숫자, 특수자를 허용하고 6~20자로 제한한다.
- `nickname`은 한글, 영어, 숫자, `_`만 허용하고 3~20자로 제한한다.

## Consequences

- 로그인과 회원가입 request schema는 같은 비밀번호 길이/문자 제약을 사용한다.
- 비밀번호 저장은 기존처럼 PBKDF2-HMAC-SHA256 hash만 저장하고 평문은 저장하지 않는다.
- DB column은 계속 `text`를 사용하며 길이와 문자 제약은 API/model validation에서 관리한다.

## Validation

- Auth endpoint validation 테스트에서 6자 ASCII 비밀번호가 통과하고, 한글 또는 공백 포함 비밀번호가 거부되는지 확인한다.
