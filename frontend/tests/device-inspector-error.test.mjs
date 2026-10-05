import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

test('successful draft retry invalidates the inspector error from the previous state', async () => {
  const slots = []; let cursor = 0;
  const react = { useState(initial) {
    const i = cursor++;
    if (!(i in slots)) slots[i] = initial;
    return [slots[i], value => { slots[i] = value; }];
  }};
  const modules = {
    react, 'antd': { Alert: 'Alert', Spin: 'Spin', Tabs: 'Tabs' },
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    './forms/DeploymentForm': { DeploymentForm: 'DeploymentForm' },
    './DeviceUsagePanel': { DeviceUsagePanel: 'DeviceUsagePanel' },
    './drafts/operations': { deviceOperation: () => ({ action: 'device_patch' }) },
  };
  const source = readFileSync(new URL('../src/features/configuration/projects/DeviceInspector.tsx', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText;
  const exports = {};
  vm.runInNewContext(compiled, {exports, Error, require: name => modules[name]});
  let context = {note: 'before'};
  const props = {device: {id: 'd'}, requiresSupply: true, execute: async () => {throw new Error('Failed to fetch');}, onApply() {}, onClose() {}};
  function render() {cursor = 0; return exports.DeviceInspector({...props, context});}
  render().props.children.find(child => child?.type === 'Tabs').props.items.find(item => item.key === 'properties').children.props.onApply({note: 'after'});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(render().props.children.find(child => child?.type === 'Alert')?.props.title, 'Failed to fetch');
  context = {note: 'after'}; // Shared retry applies the acknowledged server state.
  assert.equal(render().props.children.some(child => child?.type === 'Alert'), false);
});
