import { check } from 'k6';
import ws from 'k6/ws';
import { BASE_WS_URL } from './config.js';
import { websocketConnectSuccess, websocketPingDuration } from './metrics.js';

export function connectLobby(roomPublicId, sessionToken) {
  const url = `${BASE_WS_URL}/ws/lobby/rooms/${roomPublicId}`;
  const started = Date.now();
  const result = ws.connect(url, wsParams(sessionToken), (socket) => {
    socket.on('open', () => {
      websocketConnectSuccess.add(true, { ws: 'lobby' });
      socket.send(`{"type":"ping","payload":{"client_time":"${Date.now()}"}}`);
    });
    socket.on('message', (raw) => {
      const message = JSON.parse(raw);
      if (message.type === 'lobby.pong') {
        websocketPingDuration.add(Date.now() - started, { ws: 'lobby' });
        socket.close();
      }
    });
  });
  check(result, { 'lobby ws status 101': (res) => res && res.status === 101 });
}

function wsParams(sessionToken) {
  return {
    headers: {
      Cookie: `session_token=${sessionToken}`,
    },
  };
}
