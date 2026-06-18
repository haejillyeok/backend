import http from 'k6/http';
import { BASE_URL, TEST_ID } from './config.js';
import { expectStatus, jsonHeaders, parseJson } from './http.js';

export function createRoom(roomSize, vu, iteration) {
  const testTag = hashRoomTestId(TEST_ID);
  const response = http.post(
    `${BASE_URL}/api/v1/game/rooms`,
    JSON.stringify({
      name: `k6_${testTag}_${roomSize}_${vu}_${iteration}`.slice(0, 40),
      game_type: 'word_chain',
      max_players: Math.max(roomSize, 1),
    }),
    jsonHeaders(),
  );
  expectStatus(response, 201, 'create room');
  return parseJson(response, 'create room').data;
}

export function joinRoom(roomPublicId) {
  const response = http.post(
    `${BASE_URL}/api/v1/game/rooms/${roomPublicId}/join`,
    null,
    jsonHeaders(),
  );
  expectStatus(response, 200, 'join room');
  return parseJson(response, 'join room').data;
}

export function startRoom(roomPublicId) {
  const response = http.post(
    `${BASE_URL}/api/v1/game/rooms/${roomPublicId}/start`,
    null,
    jsonHeaders(),
  );
  expectStatus(response, 200, 'start room');
  return parseJson(response, 'start room').data;
}

function hashRoomTestId(testId) {
  let hash = 2166136261;
  for (let index = 0; index < testId.length; index += 1) {
    hash ^= testId.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36).slice(0, 6);
}
