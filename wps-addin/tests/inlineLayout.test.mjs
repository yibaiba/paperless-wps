import assert from 'node:assert/strict';
import { test } from 'node:test';

import { inlineDialogSize, INLINE_ERROR_STATUS_ROWS, BUSINESS_CANDIDATE_ROW_HEIGHT } from '../src/inlineLayout.ts';

test('inline completion stays compact and expands only for visible results', () => {
  const anchor = { anchorWidth: 100, anchorHeight: 22 };
  assert.deepEqual(inlineDialogSize({
    ...anchor, candidateCount: 0, listVisible: false, showStatus: false,
  }), { width: 240, height: 32 });
  assert.deepEqual(inlineDialogSize({
    ...anchor, candidateCount: 0, listVisible: false, showStatus: true,
  }), { width: 240, height: 62 });
  assert.deepEqual(inlineDialogSize({
    ...anchor, candidateCount: 2, listVisible: true, showStatus: false,
  }), { width: 360, height: 128 });
  assert.deepEqual(inlineDialogSize({
    ...anchor, candidateCount: 8, listVisible: true, showStatus: false,
  }), { width: 360, height: 224 });
  assert.deepEqual(inlineDialogSize({
    ...anchor,
    candidateCount: 1,
    listVisible: true,
    showStatus: true,
    windowChromeHeight: 28,
  }), { width: 360, height: 138 });
});

test('query errors reserve room for the real message and retry control', () => {
  assert.deepEqual(inlineDialogSize({ anchorWidth: 360, anchorHeight: 32,
    candidateCount: 0, listVisible: false, showStatus: true, statusRows: INLINE_ERROR_STATUS_ROWS,
  }), { width: 360, height: 92 });
});

test('business choices reserve three readable lines and scroll after four candidates', () => {
  const options = { anchorWidth: 360, anchorHeight: 32, listVisible: true, showStatus: false,
    candidateRowHeight: BUSINESS_CANDIDATE_ROW_HEIGHT };
  assert.equal(inlineDialogSize({ ...options, candidateCount: 2 }).height, 176);
  assert.equal(inlineDialogSize({ ...options, candidateCount: 8 }).height, 320);
  assert.equal(inlineDialogSize({ ...options, candidateCount: 8, listVisible: false }).height, 32);
});
