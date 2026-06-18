export const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';
export const BASE_WS_URL = __ENV.BASE_WS_URL || BASE_URL.replace(/^http/, 'ws');
export const TEST_ID = __ENV.TEST_ID || `local-${Date.now()}`;
export const PASSWORD = __ENV.K6_USER_PASSWORD || 'Loadtest123!';
export const ROOM_MIX = Object.freeze({
  one: Number(__ENV.ROOM_MIX_ONE || 50),
  two: Number(__ENV.ROOM_MIX_TWO || 20),
  three: Number(__ENV.ROOM_MIX_THREE || 15),
  four: Number(__ENV.ROOM_MIX_FOUR || 15),
});
export const TURN_SUBMIT_DELAY_MS = Number(__ENV.TURN_SUBMIT_DELAY_MS || 250);
export const MATCH_EVENT_WAIT_MS = Number(__ENV.MATCH_EVENT_WAIT_MS || 15000);
