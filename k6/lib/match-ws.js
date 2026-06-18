import { check } from 'k6';
import ws from 'k6/ws';
import { BASE_WS_URL, MATCH_EVENT_WAIT_MS } from './config.js';
import {
  websocketConnectSuccess,
  voteSubmitAcceptedRate,
  voteSubmitAttempts,
  wordSubmitAcceptedRate,
  wordSubmitAttempts,
  wordSubmitFailedRate,
  wordSubmitLatency,
  wordSubmitRejectedRate,
  wordSubmitTimeoutRate,
} from './metrics.js';
import { pickWordForTurn } from './word-pool.js';

export function connectMatchAndPlay({ gameSessionPublicId, seatNumber, sessionToken, wordPicker }) {
  const url = `${BASE_WS_URL}/ws/match?game_session_public_id=${gameSessionPublicId}`;
  let submitStartedAt = 0;
  let pendingSubmittedPhaseId = null;
  let participants = [];
  let submittedVote = false;
  const result = ws.connect(url, wsParams(sessionToken), (socket) => {
    socket.on('open', () => websocketConnectSuccess.add(true, { ws: 'match' }));
    socket.on('message', (raw) => {
      const message = JSON.parse(raw);
      if (message.type === 'match.snapshot') {
        participants = message.payload.participants || participants;
        maybeSubmitWord(socket, message.payload.current_turn, seatNumber, wordPicker, pendingSubmittedPhaseId, (phaseId) => {
          submitStartedAt = Date.now();
          pendingSubmittedPhaseId = phaseId;
        });
        submittedVote = maybeSubmitVote(socket, message.payload, seatNumber, participants, submittedVote);
      }
      if (message.type === 'match.turn.resolved') {
        if (message.payload.phase_id === pendingSubmittedPhaseId) {
          recordWordResult(message.payload.result, Date.now() - submitStartedAt);
          pendingSubmittedPhaseId = null;
          submitStartedAt = 0;
        }
        maybeSubmitWord(socket, message.payload.next_turn || null, seatNumber, wordPicker, pendingSubmittedPhaseId, (phaseId) => {
          submitStartedAt = Date.now();
          pendingSubmittedPhaseId = phaseId;
        });
        submittedVote = maybeSubmitVote(socket, message.payload, seatNumber, participants, submittedVote);
      }
      if (message.type === 'match.round.finished') {
        submittedVote = maybeSubmitVote(socket, message.payload, seatNumber, participants, submittedVote);
      }
      if (message.type === 'match.vote.accepted') {
        voteSubmitAcceptedRate.add(true);
      }
      if (message.type === 'match.result.published') {
        socket.close();
      }
    });
    socket.setTimeout(() => socket.close(), MATCH_EVENT_WAIT_MS);
  });
  check(result, { 'match ws status 101': (res) => res && res.status === 101 });
}

function wsParams(sessionToken) {
  return {
    headers: {
      Cookie: `session_token=${sessionToken}`,
    },
  };
}

export function submitVote(socket, targetSeatNumber) {
  socket.send(JSON.stringify({
    type: 'vote.submit',
    payload: { target_seat_number: targetSeatNumber },
  }));
}

function maybeSubmitVote(socket, payload, seatNumber, participants, alreadySubmitted) {
  if (alreadySubmitted || !isVotingPayload(payload)) {
    return alreadySubmitted;
  }
  const targetSeatNumber = pickVoteTargetSeatNumber(seatNumber, participants);
  if (!targetSeatNumber) {
    return alreadySubmitted;
  }
  voteSubmitAttempts.add(1);
  submitVote(socket, targetSeatNumber);
  return true;
}

function isVotingPayload(payload) {
  return payload.status === 'voting' || payload.next_status === 'voting';
}

function pickVoteTargetSeatNumber(seatNumber, participants) {
  const target = (participants || []).find((participant) => participant.seat_number !== seatNumber);
  if (target) {
    return target.seat_number;
  }
  return seatNumber === 1 ? 2 : 1;
}

function maybeSubmitWord(socket, turn, seatNumber, wordPicker, pendingSubmittedPhaseId, markSubmitted) {
  if (!turn || turn.actor_seat_number !== seatNumber) {
    return;
  }
  if (turn.phase_id === pendingSubmittedPhaseId) {
    return;
  }
  const candidate = pickWordForTurn(wordPicker, turn);
  if (!candidate) {
    return;
  }
  wordSubmitAttempts.add(1);
  markSubmitted(turn.phase_id);
  socket.send(JSON.stringify({
    type: 'word.submit',
    payload: { phase_id: turn.phase_id, word: candidate.normalized_word },
  }));
}

function recordWordResult(result, durationMs) {
  wordSubmitAcceptedRate.add(result === 'accepted');
  wordSubmitRejectedRate.add(result === 'rejected');
  wordSubmitTimeoutRate.add(result === 'timeout');
  wordSubmitFailedRate.add(result === 'failed');
  if (durationMs > 0) wordSubmitLatency.add(durationMs);
}
