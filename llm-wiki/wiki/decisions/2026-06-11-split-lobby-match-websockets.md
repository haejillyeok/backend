---
title: Split Lobby and Match WebSockets
type: decision
updated: 2026-06-12
audience: ai
---

# Split Lobby and Match WebSockets

## Decision

해질녘 게임의 실제 실시간 통신은 처음부터 로비와 매치를 분리한 WebSocket endpoint로 설계한다.

- `/ws/realtime`: ping/pong과 WebSocket 연결 테스트용 endpoint
- `/ws/lobby/rooms/{room_public_id}`: 참여가 허용된 객실의 대기방, 준비 상태, 시작 handoff, 방 채팅
- `/ws/match`: 게임 세션, 라운드, 턴, 단어 제출, 점수, 투표, 결과

`/ws/realtime`은 실제 게임 상태를 소유하거나 브로드캐스트하지 않는다.

## Rationale

- 로비와 매치는 상태 성격, 이벤트 빈도, 복구 snapshot, 권한 검증 기준이 다르다.
- 로비 room 연결은 특정 객실에 묶이며, 방 목록 조회와 방 생성/입장은 REST API가 담당한다.
- 매치 연결은 특정 게임 세션에 좁게 묶이고 라운드/턴 순서와 timer 정합성이 중요하다.
- 처음부터 endpoint를 나누면 connection manager, message handler, 테스트 범위를 작게 유지할 수 있다.

## Consequences

- 클라이언트는 REST API로 방을 생성하거나 참여한 뒤 `/ws/lobby/rooms/{room_public_id}`에 연결한다.
- 매치가 시작되면 클라이언트는 match 식별자를 받은 뒤 `/ws/match`에 연결한다.
- 매치 중에도 로비 연결을 유지할지 일시 해제할지는 UX와 부하 기준으로 별도 결정한다.
- WebSocket API 문서에서 `/ws/realtime`은 연결 테스트용으로 설명하고, 게임용 message contract는 `/ws/lobby/rooms/{room_public_id}`, `/ws/match`에 추가한다.

## Related

- [../sunset-game-domain.md](../sunset-game-domain.md)
- [../realtime-websocket.md](../realtime-websocket.md)
