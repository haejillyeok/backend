import http from 'k6/http';
import { BASE_URL, PASSWORD, TEST_ID } from './config.js';
import { expectStatus, jsonHeaders, parseJson } from './http.js';

export function createAccount(vu, iteration) {
  const testTag = hashTestId(TEST_ID);
  const suffix = `${testTag}_${vu}_${iteration}`;
  return {
    account_id: `k6_${suffix}`.slice(0, 20),
    nickname: `k6_${suffix}`.slice(0, 20),
    password: PASSWORD,
  };
}

export function signup(account) {
  const response = http.post(
    `${BASE_URL}/api/v1/auth/signup`,
    JSON.stringify(account),
    jsonHeaders(),
  );
  expectStatus(response, 201, 'signup');
  const payload = parseJson(response, 'signup').data;
  return withSessionToken(payload, extractSessionToken(response, 'signup'));
}

export function login(account) {
  const response = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ account_id: account.account_id, password: account.password }),
    jsonHeaders(),
  );
  expectStatus(response, 200, 'login');
  const payload = parseJson(response, 'login').data;
  return withSessionToken(payload, extractSessionToken(response, 'login'));
}

function extractSessionToken(response, label) {
  const cookie = response.cookies.session_token && response.cookies.session_token[0];
  if (!cookie || !cookie.value) {
    throw new Error(`${label} response did not include session_token cookie`);
  }
  return cookie.value;
}

function withSessionToken(payload, sessionToken) {
  const result = Object.assign({}, payload);
  result.sessionToken = sessionToken;
  return result;
}

function hashTestId(testId) {
  let hash = 2166136261;
  for (let index = 0; index < testId.length; index += 1) {
    hash ^= testId.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36).slice(0, 6);
}
