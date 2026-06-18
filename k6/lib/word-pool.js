import wordPool from '../fixtures/word-pool.js';
import { wordPoolMiss } from './metrics.js';

export function createWordPicker(seedOffset = 0) {
  return {
    seedOffset,
    usedByRound: {},
    offsets: {},
  };
}

export function pickWordForTurn(picker, turn) {
  const required = turn && turn.required_start_char;
  if (!required) {
    return null;
  }
  const candidates = wordPool[required] || [];
  if (candidates.length === 0) {
    wordPoolMiss.add(1, { required_start_char: required });
    return null;
  }
  const roundKey = String(turn.round_number || 1);
  const used = picker.usedByRound[roundKey] || {};
  picker.usedByRound[roundKey] = used;
  const offsetKey = `${roundKey}:${required}`;
  const startOffset = picker.offsets[offsetKey] || picker.seedOffset || 0;
  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[(startOffset + index) % candidates.length];
    if (!used[candidate.normalized_word]) {
      picker.offsets[offsetKey] = startOffset + index + 1;
      used[candidate.normalized_word] = true;
      return candidate;
    }
  }
  wordPoolMiss.add(1, { required_start_char: required });
  return null;
}
