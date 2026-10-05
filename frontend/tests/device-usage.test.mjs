import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
import { deviceChecks, usageDetails } from '../src/features/configuration/projects/usageDetails.ts';

test('usage display follows stable IDs and server quantities instead of inferring from stock or names', () => {
  const configuration = {
    devices: [{ id: 'stock', quantity: '9' }],
    rooms: [{ id: 'one', name: '会议室' }, { id: 'two', name: '会议室' }],
    systems: [{ id: 'system1', room_id: 'one', name: '无纸化' }, { id: 'system2', room_id: 'two', name: '预约' }],
    requirements: [{ id: 'role1', system_id: 'system1', role: '服务器' }, { id: 'role2', system_id: 'system2', role: '服务器' }],
  };
  const usage = { allocation_groups: [
    { id: 'one', mode: 'consumable', quantity: '1', requirement_ids: ['role1'], demand_ids: ['need1'] },
    { id: 'two', mode: 'consumable', quantity: '1', requirement_ids: ['role2'], demand_ids: ['need2'] },
  ] };
  const before = structuredClone(usage);
  const groups = usageDetails(usage, configuration);
  assert.deepEqual(groups.map(g => g.quantity), ['1', '1']);
  assert.deepEqual(groups.map(g => g.consumers[0].label), ['会议室 / 无纸化 / 服务器', '会议室 / 预约 / 服务器']);
  assert.deepEqual(usage, before);
});

test('cross-device allocation issues are visible on every affected device', () => {
  const checks = [{ code: 'resource_split_missing', device_id: 'a', device_ids: ['a', 'b'] }, { device_id: 'unrelated' }];
  assert.deepEqual(deviceChecks(checks, 'b'), [checks[0]]);
  assert.deepEqual(deviceChecks(checks, 'a'), [checks[0]]);
});

function usagePanel() {
  const require = createRequire(import.meta.url);
  const source = readFileSync(new URL('../src/features/configuration/projects/DeviceUsagePanel.tsx', import.meta.url), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const modules = {
    antd: { Alert: 'alert', Button: 'button' },
    '../shared': { useAttributeDefinitions: () => ({ data: [] }) },
    './usageDetails': { deviceChecks, usageDetails },
    './checkLabels': {}, '../EvidenceDetails': {},
  };
  const exports = {};
  vm.runInNewContext(js, { exports, require: name => name in modules ? modules[name] : require(name) });
  return exports.DeviceUsagePanel;
}

test('legacy usage details explain the original calculation without an ineffective recheck action', () => {
  const panel = usagePanel()({ deviceId: 'device', configuration: { calculation_version: 2 },
    checked: { device_usages: [], project_output: { lines: [] } }, stale: false, onRecheck() {} });
  assert.equal(panel.props.title, '历史计算版本未记录用途明细');
  assert.equal(panel.props.action, undefined);
});

test('current calculation with missing usage offers an explicit preview', () => {
  let calls = 0;
  const panel = usagePanel()({ deviceId: 'device', configuration: { calculation_version: 3 },
    checked: { device_usages: [], project_output: { lines: [] } }, stale: false, onRecheck() { calls += 1; } });
  panel.props.action.props.onClick();
  assert.equal(calls, 1);
});
