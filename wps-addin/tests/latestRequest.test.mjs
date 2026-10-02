import assert from 'node:assert/strict';
import { test } from 'node:test';

import { LatestRequest } from '../src/latestRequest.ts';
import { SUGGESTION_DEBOUNCE_MS } from '../src/constants.ts';

test('a newer suggestion request invalidates and aborts the older response', () => {
  const requests = new LatestRequest();
  const first = requests.begin();
  const second = requests.begin();

  assert.equal(first.signal.aborted, true);
  assert.equal(first.isCurrent(), false);
  assert.equal(second.signal.aborted, false);
  assert.equal(second.isCurrent(), true);
});

test('switching cells invalidates an in-flight response throughout the new debounce', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const requests = new LatestRequest();
  const previousCell = requests.begin();
  let nextCell;

  requests.schedule(SUGGESTION_DEBOUNCE_MS, (request) => { nextCell = request; });

  assert.equal(previousCell.signal.aborted, true);
  assert.equal(previousCell.isCurrent(), false);
  t.mock.timers.tick(SUGGESTION_DEBOUNCE_MS - 1);
  assert.equal(nextCell, undefined);
  t.mock.timers.tick(1);
  assert.equal(nextCell.isCurrent(), true);
  requests.cancel();
});

test('closing the editor cancels a scheduled query before any network request', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const requests = new LatestRequest();
  let queryCount = 0;
  const close = requests.schedule(SUGGESTION_DEBOUNCE_MS, () => { queryCount += 1; });

  close();
  t.mock.timers.tick(SUGGESTION_DEBOUNCE_MS);

  assert.equal(queryCount, 0);
});

test('closing the editor discards a late response even if the transport ignores abort', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const requests = new LatestRequest();
  const response = Promise.withResolvers();
  const visible = [];
  let pending;
  let transportSignal;
  const close = requests.schedule(0, (request) => {
    transportSignal = request.signal;
    pending = response.promise.then((items) => {
      if (request.isCurrent()) visible.push(...items);
    });
  });
  t.mock.timers.tick(0);

  close();
  response.resolve(['上一格的产品']);
  await pending;

  assert.equal(transportSignal.aborted, true);
  assert.deepEqual(visible, []);
});

test('cleanup from a replaced editor cannot cancel the next cell query', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const requests = new LatestRequest();
  const started = [];
  const previousCleanup = requests.schedule(SUGGESTION_DEBOUNCE_MS, () => {
    started.push('previous');
  });
  requests.schedule(0, (request) => {
    assert.equal(request.signal.aborted, false);
    started.push('next');
  });

  previousCleanup();
  t.mock.timers.tick(SUGGESTION_DEBOUNCE_MS);

  assert.deepEqual(started, ['next']);
  requests.cancel();
});
