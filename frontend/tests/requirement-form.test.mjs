import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function submit(initial, current) {
  let applied;
  const modules = {
    antd: { Form: { useForm: () => [{ getFieldsValue: () => current }] }, Modal: 'Modal', Typography: { Paragraph: 'Paragraph' } },
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    '../../RoleInput': { RoleInput: 'RoleInput' },
    '../../shared': { cleanAttributes: values => values, required: [], units: [] },
    '../../knowledge/useDefinitions': { useDefinitions: () => ({ data: undefined }) },
    '../definitionSelection': { selectedDefinition: () => undefined },
  };
  const source = readFileSync(new URL('../src/features/configuration/projects/forms/RequirementForm.tsx', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInNewContext(compiled, { exports, require: name => modules[name], crypto });
  const tree = exports.RequirementForm({ initial, systemId: 'system', devices: [], onApply: value => { applied = value; }, onClose() {} });
  // Ant Design's submitted values contain registered fields; full form state also holds preserved fields.
  const registered = { role: current.role, environment: current.environment, resources: current.resources.map(({ key, amount, unit, applies_to, target_need_key }) => ({ key, amount, unit, applies_to, target_need_key })) };
  tree.props.children.props.onFinish(registered);
  return { applied: JSON.parse(JSON.stringify(applied)) };
}

const resource = { key: 'memory', amount: '150', unit: 'GB', aggregation: 'max', capacity_basis: 'unit', applies_to: 'accessory', target_need_key: 'server' };
const role = { id: 'r', system_id: 'system', role: 'server', role_id: 'server-role', device_id: 'software', environment: [], resources: [resource] };

test('editing only an amount preserves resource aggregation, capacity basis and the role identity', () => {
  const initial = structuredClone(role);
  const current = { ...role, resources: [{ ...resource, amount: '100' }] };
  const { applied } = submit(initial, current);
  assert.deepEqual(applied.resources, current.resources);
  assert.equal(applied.id, 'r');
  assert.equal(applied.role_id, 'server-role');
  assert.deepEqual(initial, role);
});

test('removing and reordering rows does not merge a different original resource into the edit', () => {
  const cpu = { ...resource, key: 'cpu_cores', unit: '核', amount: '8', aggregation: 'sum', capacity_basis: 'deployment' };
  const initial = { ...role, resources: [resource, cpu] };
  const current = { ...initial, resources: [{ ...cpu, amount: '12' }] };
  assert.deepEqual(submit(initial, current).applied.resources, current.resources);
  const reordered = { ...initial, resources: [cpu, { ...resource, amount: '100' }] };
  assert.deepEqual(submit(initial, reordered).applied.resources, reordered.resources);
  const cleared = { ...initial, resources: [] };
  assert.deepEqual(submit(initial, cleared).applied.resources, []);
});
