# WebSocket API

BE 서버의 사용자-facing 실시간 통신 API입니다.

## Realtime

| Environment | URL |
| --- | --- |
| Production | `wss://<host>/ws/realtime` |
| Local | `ws://127.0.0.1:8000/ws/realtime` |

모든 메시지는 JSON envelope를 사용합니다.

```json
{
  "type": "ping",
  "payload": {}
}
```

### `ping`

연결과 메시지 왕복을 확인합니다. 서버는 받은 `payload`를 그대로 담아 `realtime.pong`을 반환합니다.

Client:

```json
{
  "type": "ping",
  "payload": {
    "client_time": "2026-06-11T00:00:00Z"
  }
}
```

Server:

```json
{
  "type": "realtime.pong",
  "payload": {
    "client_time": "2026-06-11T00:00:00Z"
  }
}
```

## Error

잘못된 JSON, envelope 형식 오류, 지원하지 않는 message type은 서버가 `error` envelope를 보낸 뒤
`VALIDATION_ERROR`의 WebSocket close code인 `1008`로 연결을 종료합니다.

```json
{
  "type": "error",
  "payload": {
    "success": false,
    "data": null,
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "요청 값이 올바르지 않습니다.",
      "details": {
        "reason": "unsupported_message_type",
        "type": "unknown"
      }
    }
  }
}
```

## Docs Route

이 문서는 BE 서버에서 `GET /ws-docs`로 조회할 수 있습니다.

## Test Client

- [Hoppscotch WebSocket client](https://hoppscotch.io/realtime/websocket)에서 WebSocket 연결과 메시지 송수신을 테스트할 수 있습니다.
