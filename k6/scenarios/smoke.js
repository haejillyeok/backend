import { Trend } from 'k6/metrics';
import { createAccount, login, signup } from '../lib/auth.js';
import { createRoom, joinRoom, startRoom } from '../lib/rooms.js';
import {
  claimAssignment,
  markReady,
  publishRoom,
  publishSession,
  waitForAllReady,
  waitForRoom,
  waitForSession,
} from '../lib/coordinator.js';
import { connectLobby } from '../lib/lobby-ws.js';
import { connectMatchAndPlay } from '../lib/match-ws.js';
import { createWordPicker } from '../lib/word-pool.js';
import { e2eCycleDuration } from '../lib/metrics.js';

export const options = {
  scenarios: {
    smoke: {
      executor: 'shared-iterations',
      vus: smokeVus(),
      iterations: smokeIterations(),
      maxDuration: __ENV.SMOKE_DURATION || '1m',
    },
  },
  thresholds: {
    checks: ['rate>0.95'],
    http_req_failed: ['rate<0.05'],
    word_submit_accepted_rate: ['rate>0.95'],
    word_submit_rejected_rate: ['rate<0.05'],
  },
};

const smokeCycle = new Trend('smoke_cycle_duration', true);

function smokeVus() {
  return Number(__ENV.SMOKE_VUS || 1);
}

function smokeIterations() {
  return Number(__ENV.SMOKE_ITERATIONS || smokeVus());
}

export default function () {
  const started = Date.now();
  const assignment = claimAssignment(__VU, __ITER, roomSizeOverride());
  const account = createAccount(__VU, __ITER);
  signup(account);
  const loginResult = login(account);

  let roomPublicId;
  if (assignment.is_owner) {
    const room = createRoom(assignment.room_size, __VU, __ITER);
    roomPublicId = room.room_public_id;
    publishRoom(assignment.group_id, roomPublicId);
  } else {
    roomPublicId = waitForRoom(assignment.group_id);
    joinRoom(roomPublicId);
  }

  connectLobby(roomPublicId, loginResult.sessionToken);
  markReady(assignment.group_id, assignment.slot_index);

  let gameSessionPublicId;
  if (assignment.is_owner) {
    waitForAllReady(assignment.group_id);
    const session = startRoom(roomPublicId);
    gameSessionPublicId = session.game_session_public_id;
    publishSession(assignment.group_id, gameSessionPublicId);
  } else {
    gameSessionPublicId = waitForSession(assignment.group_id);
  }

  connectMatchAndPlay({
    gameSessionPublicId,
    seatNumber: assignment.slot_index + 1,
    sessionToken: loginResult.sessionToken,
    wordPicker: createWordPicker(assignment.slot_index),
  });
  const duration = Date.now() - started;
  smokeCycle.add(duration);
  e2eCycleDuration.add(duration, { room_size: String(assignment.room_size) });
}

function roomSizeOverride() {
  if (!__ENV.K6_ROOM_SIZE) return null;
  return Number(__ENV.K6_ROOM_SIZE);
}
