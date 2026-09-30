import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import vm from 'node:vm';

async function addinMain() {
  const values = new Map();
  const localValues = new Map();
  const onKey = [];
  const sent = [];
  const executed = [];
  const window = {
    location: { href: 'http://127.0.0.1:3889/index.html' },
    Application: {
      PluginStorage: {
        getItem: (key) => values.get(key),
        setItem: (key, value) => values.set(key, String(value)),
      },
      OnKey: (...args) => onKey.push(args),
      SendKeys: (key) => sent.push(key),
      GetWebDialog: () => ({
        ExecuteJavaScript: (script) => executed.push(script),
      }),
    },
    localStorage: {
      getItem: (key) => localValues.get(key),
      setItem: (key, value) => localValues.set(key, String(value)),
    },
  };
  const source = await readFile(new URL('../public/main.js', import.meta.url), 'utf8');
  vm.runInNewContext(source, { window, alert: () => {} });
  return { executed, localValues, onKey, sent, values, window };
}

test('global WPS Tab callback forwards the active completion session to the inline dialog', async () => {
  const context = await addinMain();
  context.values.set('presales_inline_dialog_id', '7');
  context.values.set('presales_tab_session', JSON.stringify({
    session_id: 'session-1', revision: 'ghost:0', status: 'ready',
  }));

  assert.equal(context.window.PresalesTab(), true);
  assert.match(context.executed[0], /PresalesInlineTab\("session-1"\)/);
  assert.deepEqual(context.sent, []);
});

test('stale global Tab registration restores and replays native Tab', async () => {
  const context = await addinMain();

  for (let index = 0; index < 100; index += 1) {
    assert.equal(context.window.PresalesTab(), false);
  }
  assert.deepEqual(context.onKey.at(-1), ['{TAB}']);
  assert.equal(context.sent.length, 100);
  assert.ok(context.sent.every((key) => key === '{TAB}'));
});
