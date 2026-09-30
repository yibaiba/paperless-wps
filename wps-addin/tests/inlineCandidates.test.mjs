import assert from 'node:assert/strict';
import { test } from 'node:test';

import { prioritizeInlineCandidates } from '../src/inlineCandidates.ts';

function candidate(key, model, source) {
  return { key, model, name: `${model} 产品`, source_id: source };
}

test('inline candidates show every top-product choice before diversifying other products', () => {
  const candidates = [
    candidate('a:1', 'A', 'source-1'),
    candidate('b:1', 'B', 'source-1'),
    candidate('b:2', 'B', 'source-2'),
    candidate('c:1', 'C', 'source-1'),
    candidate('a:2', 'A', 'source-2'),
    candidate('d:1', 'D', 'source-1'),
  ];

  const visible = prioritizeInlineCandidates(candidates, 5);

  assert.deepEqual(visible.map((item) => item.key), ['a:1', 'a:2', 'b:1', 'c:1', 'd:1']);
  assert.deepEqual(candidates.map((item) => item.key), [
    'a:1', 'b:1', 'b:2', 'c:1', 'a:2', 'd:1',
  ]);
});

test('inline candidate prioritization respects an empty or bounded viewport', () => {
  const candidates = [candidate('a:1', 'A', 'source-1'), candidate('b:1', 'B', 'source-1')];

  assert.deepEqual(prioritizeInlineCandidates(candidates, 0), []);
  assert.deepEqual(prioritizeInlineCandidates(candidates, 1).map((item) => item.key), ['a:1']);
});
