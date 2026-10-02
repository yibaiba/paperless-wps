import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';

import { InlineDialogManager } from '../src/inlineDialog.ts';
import { LatestRequest } from '../src/latestRequest.ts';

function liveDialog() {
  const storage = new Map();
  const window = { focus: () => {}, PresalesInlineRefresh: () => {} };
  const dialog = {
    ID: 1,
    Resize: () => {},
    Move: () => {},
    ExecuteJavaScript: (script) => runInNewContext(script, { window }),
    Visible: false,
  };
  const app = {
    Selection: { Left: 100, Top: 200, Width: 100, Height: 20 },
    ActiveWindow: {
      PointsToScreenPixelsX: (value) => value,
      PointsToScreenPixelsY: (value) => value,
    },
    CreateWebDialog: () => dialog,
    GetWebDialog: () => dialog,
  };
  const manager = new InlineDialogManager({
    app,
    href: 'http://127.0.0.1:3889/taskpane.html',
    get: (key) => storage.get(key) ?? null,
    set: (key, value) => storage.set(key, String(value)),
  });
  return { manager, window, dialog, app };
}

test('hiding a persistent dialog notifies its editor to cancel without taking focus', () => {
  const { manager, window, dialog } = liveDialog();
  const requests = new LatestRequest();
  manager.show({ profile: { id: 'profile' }, cell: { row: 2 } });
  const pending = requests.begin();
  window.PresalesInlineRefresh = () => {
    if (!manager.context()) requests.cancel();
  };
  window.focus = () => assert.fail('hidden editor must not take WPS focus');

  manager.hide();

  assert.equal(dialog.Visible, false);
  assert.equal(pending.signal.aborted, true);
  assert.equal(pending.isCurrent(), false);
});

test('a hidden dialog does not read WPS geometry after the workbook closes', () => {
  const { manager, app } = liveDialog();
  manager.show({ profile: { id: 'profile' }, cell: { row: 2 } });
  manager.hide();
  Object.defineProperty(app, 'Selection', {
    get: () => assert.fail('hidden dialog must not access the current cell'),
  });
  Object.defineProperty(app, 'ActiveWindow', {
    get: () => assert.fail('closed workbook has no active window'),
  });

  manager.layout({ candidateCount: 0, listVisible: false, showStatus: false });
});

test('inline dialog keeps a monotonic context nonce and follows the selected cell', () => {
  const storage = new Map();
  const moves = [];
  const sizes = [];
  const createArguments = [];
  let getDialogCalls = 0;
  const executedScripts = [];
  const dialog = {
    ID: 7,
    Resize: (width, height) => sizes.push([width, height]),
    Move: (x, y) => moves.push([x, y]),
    ExecuteJavaScript: (script) => executedScripts.push(script),
    Visible: false,
  };
  const app = {
    Selection: { Left: 100, Top: 200, Width: 100, Height: 20 },
    ActiveWindow: {
      PointsToScreenPixelsX: (value) => value,
      PointsToScreenPixelsY: (value) => value,
    },
    CreateWebDialog: (...args) => {
      createArguments.push(args);
      return dialog;
    },
    GetWebDialog: () => { getDialogCalls += 1; return dialog; },
  };
  const manager = new InlineDialogManager({
    app, href: 'http://127.0.0.1:3889/taskpane.html',
    screen: { availWidth: 1000, availHeight: 300 },
    get: (key) => storage.get(key) ?? null,
    set: (key, value) => storage.set(key, String(value)),
  });
  const value = { profile: { id: 'p1' }, cell: { row: 2 } };
  manager.show(value);
  const firstNonce = manager.context().nonce;
  assert.ok(firstNonce > 0);
  assert.deepEqual(manager.context().anchor, { width: 100, height: 20 });
  assert.deepEqual(createArguments[0].slice(2), [
    240, 32, false, false, 2, '', 0, true, false, true,
  ]);
  assert.match(executedScripts[0], /window\.focus\(\)/);
  assert.deepEqual(moves, [[100, 200]]);
  assert.equal(manager.layout({
    candidateCount: 8,
    listVisible: true,
    showStatus: false,
  }).placement, 'above');
  assert.deepEqual(sizes.at(-1), [360, 224]);
  assert.deepEqual(moves.at(-1), [100, 0]);
  const stableSizeCount = sizes.length;
  const stableMoveCount = moves.length;
  manager.layout({ candidateCount: 8, listVisible: true, showStatus: false });
  assert.equal(sizes.length, stableSizeCount);
  assert.equal(moves.length, stableMoveCount);
  assert.equal(getDialogCalls, 0);
  app.Selection.Left = 900;
  manager.layout({ candidateCount: 1, listVisible: true, showStatus: false });
  assert.deepEqual(moves.at(-1), [640, 200]);
  manager.hide();
  const firstSession = manager.context();
  assert.equal(firstSession, null);
  manager.show(value);
  assert.ok(manager.context().nonce > firstNonce);
  assert.equal(createArguments.length, 1);
  assert.equal(executedScripts.filter((script) => script === 'window.close()').length, 0);
  assert.equal(dialog.Visible, true);
});
