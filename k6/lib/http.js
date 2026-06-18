import { check, fail } from 'k6';

export function jsonHeaders(extra = {}) {
  const headers = { 'Content-Type': 'application/json' };
  Object.keys(extra).forEach((key) => {
    headers[key] = extra[key];
  });
  return { headers };
}

export function parseJson(response, label) {
  try {
    return response.json();
  } catch (error) {
    fail(`${label} returned non-JSON body status=${response.status}`);
  }
  return null;
}

export function expectStatus(response, expected, label) {
  const ok = check(response, {
    [`${label} status ${expected}`]: (res) => res.status === expected,
  });
  if (!ok) {
    fail(`${label} expected status=${expected} actual=${response.status} body=${response.body}`);
  }
}
