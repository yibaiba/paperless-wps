import test from 'node:test';
import assert from 'node:assert/strict';
import { setupFields, setupPayload } from '../src/features/configuration/projects/forms/setupModel.ts';

const count = { key: 'terminals', label: '终端数量', kind: 'quantity', unit: '台', scope: 'system', purpose: 'project_input', evidence: [] };
const os = { key: 'os', label: '操作系统', kind: 'text', unit: '', scope: 'role', purpose: 'product_requirement', evidence: [] };
const description = { name: '隔离系统', roles: [{ id: 'software', inputs: [count, os] }, { id: 'server', inputs: [count] }] };

test('prospective fields share system scale but never spread software environment to hardware', () => {
  const fields = setupFields(description, ['software', 'server']);
  assert.equal(fields.length, 2);
  const configuration = { systems: [], requirements: [], devices: [] };
  const payload = setupPayload({ configuration, systemId: 's', roomId: 'r', description, fields,
    values: { name: '会议室系统', definition_id: 'def', role_ids: ['software', 'server'], inputs: { [fields[0].formKey]: '2.5', [fields[1].formKey]: 'Windows' } } });
  assert.equal(payload.system.inputs[0].value, '2.5');
  assert.equal(payload.role_environment.software[0].value, 'Windows');
  assert.equal(payload.role_environment.server, undefined);
  assert.deepEqual(configuration, { systems: [], requirements: [], devices: [] });
});

test('blank stays unknown, existing unrelated inputs and device assignments remain untouched', () => {
  const configuration = { systems: [{ id: 's', inputs: [{ key: 'legacy', value: 'keep', kind: 'text', unit: '' }] }],
    requirements: [{ id: 'old', system_id: 's', role_id: 'software', device_id: 'd', environment: [{ key: 'legacy', value: 'keep', kind: 'text', unit: '' }] }], devices: [{ id: 'd' }] };
  const baseline = structuredClone(configuration);
  const fields = setupFields(description, ['software']);
  const payload = setupPayload({ configuration, systemId: 's', roomId: 'r', description, fields,
    values: { name: '隔离', definition_id: 'def', role_ids: ['software'], inputs: {} } });
  assert.equal(payload.system.inputs.find(x => x.key === 'terminals').value, null);
  assert.equal(payload.system.inputs.find(x => x.key === 'legacy').value, 'keep');
  assert.equal(payload.role_environment.software.find(x => x.key === 'os').value, null);
  assert.deepEqual(configuration, baseline);
});

test('a historical value is never relabelled to a new unit without explicit input', () => {
  const configuration = { systems: [{ id: 's', inputs: [{ key: 'terminals', value: '8', kind: 'quantity', unit: '套' }] }], requirements: [] };
  const options = { configuration, systemId: 's', roomId: 'r', description, fields: setupFields(description, ['server']), values: { name: '隔离', definition_id: 'def', role_ids: ['server'], inputs: {} } };
  assert.throws(() => setupPayload(options), /单位已变化/);
  options.values.inputs[options.fields[0].formKey] = '16';
  assert.equal(setupPayload(options).system.inputs[0].value, '16');
  assert.equal(configuration.systems[0].inputs[0].value, '8');
});
