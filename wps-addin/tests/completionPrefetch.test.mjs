import assert from 'node:assert/strict';
import { test } from 'node:test';

import { CompletionPrefetch, completionPrefetchKey } from '../src/completionPrefetch.ts';

test('next-row completion reuses the request started by the accepted row', async () => {
  const prefetch = new CompletionPrefetch();
  let loads = 0;
  prefetch.start('row-2', async () => {
    loads += 1;
    return ['CRIR-D-WE'];
  });

  const outcome = await prefetch.take('row-2');

  assert.deepEqual(outcome, { value: ['CRIR-D-WE'] });
  assert.equal(loads, 1);
  assert.equal(prefetch.take('row-2'), undefined);
});

test('prefetch preserves a real request error for the next editor', async () => {
  const prefetch = new CompletionPrefetch();
  prefetch.start('row-3', async () => { throw new Error('network unavailable'); });

  const outcome = await prefetch.take('row-3');

  assert.equal(outcome.error.message, 'network unavailable');
});

test('prefetch identity is scoped to workbook, profile and cell', () => {
  assert.equal(completionPrefetchKey({
    workbookInstanceId: 'workbook',
    profileId: 'profile',
    profileRevision: 2,
    sheet: '报价表',
    row: 8,
    column: 3,
  }), 'workbook:profile@2:报价表:8:3');
});
