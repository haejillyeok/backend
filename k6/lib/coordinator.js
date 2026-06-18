import http from 'k6/http';
import { sleep } from 'k6';
import { TEST_ID } from './config.js';
import { expectStatus, jsonHeaders, parseJson } from './http.js';
import { roomCoordinationFailures } from './metrics.js';

export const K6_COORDINATOR_URL = __ENV.K6_COORDINATOR_URL || 'http://127.0.0.1:8787';

export function claimAssignment(vu, iteration, roomSize = null) {
  const body = { test_id: TEST_ID, vu, iteration };
  if (roomSize) body.room_size = roomSize;
  const response = http.post(
    `${K6_COORDINATOR_URL}/assignments/claim`,
    JSON.stringify(body),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'claim assignment');
  return parseJson(response, 'claim assignment');
}

export function publishRoom(groupId, roomPublicId) {
  const response = http.post(
    `${K6_COORDINATOR_URL}/groups/${groupId}/room`,
    JSON.stringify({ room_public_id: roomPublicId }),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'publish room');
}

export function waitForRoom(groupId) {
  return waitForValue(`/groups/${groupId}/room`, 'room_public_id');
}

export function markReady(groupId, slotIndex) {
  const response = http.post(
    `${K6_COORDINATOR_URL}/groups/${groupId}/ready`,
    JSON.stringify({ slot_index: slotIndex }),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'mark ready');
}

export function waitForAllReady(groupId) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const response = http.get(`${K6_COORDINATOR_URL}/groups/${groupId}/ready`);
    expectStatus(response, 200, 'get ready');
    const payload = parseJson(response, 'get ready');
    if (payload.all_ready) return payload;
    sleep(0.2);
  }
  roomCoordinationFailures.add(1, { phase: 'ready' });
  return null;
}

export function publishSession(groupId, gameSessionPublicId) {
  const response = http.post(
    `${K6_COORDINATOR_URL}/groups/${groupId}/session`,
    JSON.stringify({ game_session_public_id: gameSessionPublicId }),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'publish session');
}

export function waitForSession(groupId) {
  return waitForValue(`/groups/${groupId}/session`, 'game_session_public_id');
}

function waitForValue(path, key) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const response = http.get(`${K6_COORDINATOR_URL}${path}`);
    if (response.status === 200) {
      const payload = parseJson(response, path);
      if (payload[key]) return payload[key];
    }
    sleep(0.2);
  }
  roomCoordinationFailures.add(1, { phase: key });
  return null;
}
