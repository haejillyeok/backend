---
title: Realtime WebSocket
type: api-contract
updated: 2026-06-11
audience: ai
---

# Realtime WebSocket

BE 서버는 WebSocket 연결 테스트용 endpoint를 `/ws/realtime`에 둔다.
운영 HTTPS/TLS 앞단에서는 같은 path를 `wss://<host>/ws/realtime`로 연결한다.
로컬 개발에서는 `ws://127.0.0.1:8000/ws/realtime`를 사용한다.

`/ws/realtime`은 ping/pong과 envelope validation 확인을 위한 채널이다.
해질녘 게임의 실제 실시간 상태는 처음부터 `/ws/lobby`, `/ws/match`처럼 목적별
endpoint로 분리한다.

## Code Map

- Endpoint: `app/be/api/endpoints/realtime_ws.py`
- HTML docs endpoint: `app/be/api/endpoints/ws_docs.py`
- Connection manager and message handling: `app/be/services/realtime.py`
- Socket router include: `app/be/api/socket_router.py`
- Contract tests: `test/test_realtime_websocket.py`
- API-served docs source: `app/be/api/docs/ws-api.md`

## Docs Route

BE 서버는 WebSocket API 전용 문서 페이지를 `GET /ws-docs`에서 `text/html`로 반환한다.
문서 원본은 `app/be/api/docs/ws-api.md`이며, Docker image에 포함되도록 `docs/`가 아니라 `app/` 아래에서
관리한다. 라우터는 이 Markdown 원본을 HTML 페이지로 렌더링한다. WebSocket message contract가 늘어나면
이 파일을 먼저 갱신한다.

## Message Contract

모든 메시지는 JSON envelope를 사용한다.

```json
{
  "type": "ping",
  "payload": {}
}
```

현재 지원하는 client message type은 `ping` 하나다. 서버는 같은 payload를 담아
`realtime.pong`을 반환한다.

```json
{
  "type": "realtime.pong",
  "payload": {}
}
```

잘못된 JSON, envelope 형식 오류, 지원하지 않는 message type은 `error` envelope를 보낸 뒤
`VALIDATION_ERROR`의 WebSocket close code인 `1008`로 연결을 닫는다.

## Design Notes

- TLS 자체는 FastAPI endpoint가 아니라 배포/프록시 계층에서 종단한다.
- `/ws/realtime`은 게임 상태를 소유하거나 브로드캐스트하지 않는다.
- 실제 게임용 WebSocket은 기능별 endpoint와 connection manager를 별도로 둔다.
- 앱 코드는 각 WebSocket endpoint와 JSON message contract를 소유한다.
- Connection manager는 active connection registry와 cleanup을 담당한다.
- 이후 세션 인증이 필요하면 연결 수락 전 쿠키 또는 token을 검증하고, 인증 실패는 `1008` close code로 닫는다.

## Related

- [backend-guidelines.md](backend-guidelines.md)
- [code-conventions.md](code-conventions.md)
- [decisions/2026-06-11-split-lobby-match-websockets.md](decisions/2026-06-11-split-lobby-match-websockets.md)
