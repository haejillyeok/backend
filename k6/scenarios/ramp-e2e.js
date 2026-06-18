import smokeDefault from './smoke.js';
import { connectMatchAndPlay } from '../lib/match-ws.js';

export const options = {
  scenarios: {
    ramp_e2e: {
      executor: 'ramping-vus',
      stages: [
        { duration: '1m', target: 10 },
        { duration: '3m', target: 10 },
        { duration: '1m', target: 50 },
        { duration: '5m', target: 50 },
        { duration: '1m', target: 100 },
        { duration: '5m', target: 100 },
        { duration: '1m', target: 0 },
      ],
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
