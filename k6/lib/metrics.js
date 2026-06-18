import { Counter, Rate, Trend } from 'k6/metrics';

export const e2eCycleDuration = new Trend('e2e_cycle_duration', true);
export const roomCoordinationFailures = new Counter('room_coordination_failures');
export const websocketConnectSuccess = new Rate('websocket_connect_success');
export const websocketPingDuration = new Trend('websocket_ping_duration', true);
export const wordSubmitAttempts = new Counter('word_submit_attempts');
export const wordSubmitAcceptedRate = new Rate('word_submit_accepted_rate');
export const wordSubmitRejectedRate = new Rate('word_submit_rejected_rate');
export const wordSubmitTimeoutRate = new Rate('word_submit_timeout_rate');
export const wordSubmitFailedRate = new Rate('word_submit_failed_rate');
export const wordPoolMiss = new Counter('word_pool_miss');
export const wordSubmitLatency = new Trend('word_submit_latency', true);
export const voteSubmitAttempts = new Counter('vote_submit_attempts');
export const voteSubmitAcceptedRate = new Rate('vote_submit_accepted_rate');
