import smokeDefault from './smoke.js';
import { connectMatchAndPlay } from '../lib/match-ws.js';

export const options = {
  scenarios: {
    soak_e2e: {
      executor: 'constant-vus',
      vus: Number(__ENV.SOAK_VUS || 50),
      duration: __ENV.SOAK_DURATION || '30m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.10'],
    checks: ['rate>0.90'],
  },
};

export default smokeDefault;

export const scenarioUses = {
  connectMatchAndPlay,
};
