import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

test('unchanged business facts can adopt, undo and redo a distinct calculation checkpoint', () => {
  const slots = []; let cursor = 0;
  const react = {
    useRef(value) { const i = cursor++; return slots[i] ??= { current: value }; },
    useState(value) {
      const i = cursor++; if (!(i in slots)) slots[i] = value;
      return [slots[i], v => { slots[i] = typeof v === 'function' ? v(slots[i]) : v; }];
    },
  };
  const file = new URL('../src/features/configuration/useConfigurationDraft.ts', import.meta.url);
  const js = ts.transpileModule(readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports, require: name => name === 'react' ? react : { configurationKey: JSON.stringify } });
  const config = { devices: [{ id: 'same' }] };
  const render = () => { cursor = 0; return exports.useConfigurationDraft(config); };
  render().commit(config, 'recheck');
  assert.equal(render().canUndo, true);
  assert.equal(render().historyKey, 'recheck');
  render().undo();
  assert.equal(render().historyKey, '');
  assert.equal(render().present, config);
  render().redo();
  assert.equal(render().historyKey, 'recheck');
  render().commit({ devices: [] });
  render().undo();
  assert.equal(render().historyKey, 'recheck');
  assert.equal(render().present, config);
});
