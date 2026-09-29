import { test } from 'node:test';
import assert from 'node:assert/strict';
import { selectedDefinition, requiredRoleLabel, requestedRole } from '../src/features/configuration/projects/definitionSelection.ts';

test('project roles use package-pinned definition instead of newer definition', () => {
  const pinned={id:'d',revision:1,roles:[{id:'old'}]};
  const latest={id:'d',revision:2,roles:[{id:'new'}]};
  const definitions={definitions:[latest],packages:[{id:'p',definition:pinned}]};
  assert.equal(selectedDefinition({definition_id:'d',knowledge_package_id:'p'},definitions),pinned);
  assert.equal(selectedDefinition({definition_id:'d'},definitions),latest);
  assert.equal(selectedDefinition({definition_id:'missing'},definitions),undefined);
});
test('unconfirmed roles are not represented as optional or required purchases', () => {
  assert.equal(requiredRoleLabel({required:false,feature:''},'draft'),'必要性待核对');
  assert.equal(requiredRoleLabel({required:true,feature:'投票'},'draft'),'启用「投票」时核对必要性');
  assert.equal(requiredRoleLabel({required:true,feature:'投票'},'confirmed'),'启用「投票」时必需');
  assert.equal(requiredRoleLabel({required:true,feature:''},'confirmed'),'基础必需角色');
});
test('missing role actions prefill only the exact role and do not invent one', () => {
  assert.deepEqual(requestedRole({role_id:'voting',role_name:'投票客户端'}),{id:'voting',name:'投票客户端'});
  assert.equal(requestedRole({role_id:'voting'}),undefined);
  assert.equal(requestedRole({}),undefined);
});
