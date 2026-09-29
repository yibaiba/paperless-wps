import { test } from 'node:test';
import assert from 'node:assert/strict';
import { requirementDeviceIds, unlinkRoleDevice } from '../src/features/configuration/projects/roleAllocations.ts';
import { configurationOperations } from '../src/features/configuration/projects/drafts/operations.ts';

test('partial reuse retains both identities and removes only the deleted batch', () => {
  const role = { id: 'role', device_id: null, allocations: [
    { device_id: 'existing', quantity: '16', evidence: 'existing' },
    { device_id: 'new', quantity: '16', evidence: 'purchase' },
  ] };
  assert.deepEqual(requirementDeviceIds(role), ['existing', 'new']);
  const after = unlinkRoleDevice(role, 'new');
  assert.deepEqual(requirementDeviceIds(after), ['existing']);
  assert.equal(role.allocations.length, 2);
  const base = { rooms: [], systems: [], devices: [], requirements: [role], accessory_allocations: [], drawing_xml: '', actor: '', evidence: '' };
  const operations = configurationOperations(base, { ...base, requirements: [after] });
  assert.deepEqual(operations, [{ action: 'requirement_put', value: after }]);
});

test('legacy single-device binding stays supported', () => {
  assert.deepEqual(requirementDeviceIds({ device_id: 'one' }), ['one']);
  assert.deepEqual(requirementDeviceIds(unlinkRoleDevice({ device_id: 'one' }, 'one')), []);
});
