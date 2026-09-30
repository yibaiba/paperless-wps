import assert from 'node:assert/strict';
import { test } from 'node:test';

import { nextCandidateIndex } from '../src/inlineNavigation.ts';
import { ghostCompletion } from '../src/inlineCompletion.ts';

test('candidate keyboard navigation wraps in both directions', () => {
  assert.equal(nextCandidateIndex(0, 3, 1), 1);
  assert.equal(nextCandidateIndex(2, 3, 1), 0);
  assert.equal(nextCandidateIndex(0, 3, -1), 2);
  assert.equal(nextCandidateIndex(0, 0, 1), 0);
});

test('ghost completion previews name or model suffix without guessing a fuzzy match', () => {
  const candidate = {
    name: '对接OA系统', model: 'CRIR-D-OA', confidence: 'high', completion_ready: true,
  };
  assert.deepEqual(ghostCompletion('', candidate), { prefix: '', suffix: '对接OA系统' });
  assert.deepEqual(ghostCompletion('', candidate, 'model'), { prefix: '', suffix: 'CRIR-D-OA' });
  assert.deepEqual(ghostCompletion('对接OA', candidate), { prefix: '对接OA', suffix: '系统' });
  assert.deepEqual(ghostCompletion('crir-d', candidate), { prefix: 'CRIR-D', suffix: '-OA' });
  assert.deepEqual(ghostCompletion('对接OA系统', candidate), {
    prefix: '对接OA系统', suffix: '',
  });
  assert.equal(ghostCompletion('OA', candidate), null);
  assert.equal(ghostCompletion(' 对接', candidate), null);
  assert.equal(ghostCompletion('', { ...candidate, confidence: 'medium' }), null);
});
