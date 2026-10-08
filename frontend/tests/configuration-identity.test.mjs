import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(
  new URL('../src/features/configuration/projects/configurationIdentity.ts', import.meta.url),
  'utf8',
);
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exports = {};
vm.runInNewContext(js, { exports, WeakMap, JSON });

test('business identity ignores drawing layout but detects business changes', () => {
  const original = { devices: [{ id: 'server', quantity: '1' }], drawing_xml: '<old />' };
  const moved = { ...structuredClone(original), drawing_xml: '<moved />' };
  const changed = structuredClone(original);
  changed.devices[0].quantity = '2';

  assert.equal(exports.businessKey(original), exports.businessKey(moved));
  assert.notEqual(exports.businessKey(original), exports.businessKey(changed));
});

test('configuration identity still includes drawing layout', () => {
  const original = { devices: [], drawing_xml: '<old />' };
  const moved = { ...original, drawing_xml: '<moved />' };

  assert.notEqual(exports.configurationKey(original), exports.configurationKey(moved));
});
