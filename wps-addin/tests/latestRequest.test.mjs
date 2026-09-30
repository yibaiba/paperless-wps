import assert from 'node:assert/strict';
import { test } from 'node:test';

import { LatestRequest } from '../src/latestRequest.ts';

test('a newer suggestion request invalidates and aborts the older response', () => {
  const requests = new LatestRequest();
  const first = requests.begin();
  const second = requests.begin();

  assert.equal(first.signal.aborted, true);
  assert.equal(first.isCurrent(), false);
  assert.equal(second.signal.aborted, false);
  assert.equal(second.isCurrent(), true);
});
