import test from 'node:test';
import assert from 'node:assert/strict';
import { BusinessPrefetch } from '../src/businessPrefetch.ts';

test('an adopted prefetch follows the current query cancellation signal', async () => {
  const cache = new BusinessPrefetch(), request = new AbortController();
  let transportSignal;
  cache.start('next', (signal) => {
    transportSignal = signal;
    return new Promise((_, reject) => signal.addEventListener('abort', () => reject(new Error('cancelled'))));
  });
  const result = cache.take('next', request.signal);
  request.abort();
  assert.equal(transportSignal.aborted, true);
  assert.match((await result).error.message, /cancelled/);
});

test('a query already cancelled cannot adopt a running prefetch', async () => {
  const cache = new BusinessPrefetch(), request = new AbortController();
  let transportSignal;
  cache.start('next', async (signal) => { transportSignal = signal; return { items: [] }; });
  request.abort();
  await cache.take('next', request.signal);
  assert.equal(transportSignal.aborted, true);
});

test('settled prefetch removes its cancellation listener and is consumed once', async () => {
  const cache = new BusinessPrefetch(), request = new AbortController();
  let transportSignal, removed = 0;
  const remove = request.signal.removeEventListener.bind(request.signal);
  request.signal.removeEventListener = (...args) => { removed++; remove(...args); };
  cache.start('next', async (signal) => { transportSignal = signal; return { items: [] }; });
  assert.deepEqual(await cache.take('next', request.signal), { value: { items: [] } });
  assert.equal(cache.take('next', request.signal), undefined);
  assert.equal(removed, 1);
  request.abort();
  assert.equal(transportSignal.aborted, false);
});
