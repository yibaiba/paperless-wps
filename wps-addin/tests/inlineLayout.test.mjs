import assert from 'node:assert/strict';
import { test } from 'node:test';

import { inlineDialogSize } from '../src/inlineLayout.ts';

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
