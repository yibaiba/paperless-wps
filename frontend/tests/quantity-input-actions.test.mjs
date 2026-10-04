import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyQuantityInputs } from '../src/features/configuration/projects/forms/quantityInputEdits.ts';
import { accessoryOpenItems } from '../src/features/configuration/projects/accessoryOpenItems.ts';

const input = { code: 'quantity_input_missing', key: 'seats', label: '席位', scope: 'system', scope_id: 's', unit: '台', kind: 'quantity', message: '需要补填' };
const value = n => ({key:'seats',kind:'quantity',value:n,unit:'台'});
const config = { rooms:[{id:'r',name:'会议室'},{id:'other',name:'会议室'}], systems:[{id:'s',inputs:[{key:'custom',kind:'text',value:'保留',unit:''}]}], requirements:[{id:'role',environment:[]}], project_inputs:[value('100')], room_inputs:{other:[value('7')]}, devices:[] };
const suggestion = { id:'d',rule:{id:'rule',name:'授权'},scope_id:'s',status:'unknown',selected:true,missing_information:['缺少数量'],input_issues:[input],input_issues_only:true };

test('input and knowledge tasks remain separate without matching message text', () => {
  const rows = accessoryOpenItems(suggestion, config);
  assert.equal(rows.length, 1); assert.equal(rows[0].category, '需求');
  assert.deepEqual(rows[0].action.quantity_inputs, [input]);
  assert.equal(accessoryOpenItems({...suggestion,input_issues_only:false},config).length,2);
  assert.equal(accessoryOpenItems({...suggestion,selected:false},config).length,0);
});
test('one immutable edit preserves other scopes, fields, zero and unknown', () => {
  const before = structuredClone(config);
  const next = applyQuantityInputs(config,[input,{...input,scope:'room',scope_id:'r'},{...input,scope:'role',scope_id:'role'}],['3','0',null]);
  assert.equal(next.systems[0].inputs.find(i=>i.key==='seats').value,'3');
  assert.equal(next.systems[0].inputs[0].key,'custom');
  assert.equal(next.room_inputs.r[0].value,'0');
  assert.equal(next.requirements[0].environment[0].value,null);
  assert.deepEqual(next.project_inputs,config.project_inputs);
  assert.deepEqual(next.room_inputs.other,config.room_inputs.other);
  assert.deepEqual(config,before);
});
test('stale scope errors do not silently discard or partially change inputs', () => {
  const before = structuredClone(config);
  assert.throws(()=>applyQuantityInputs(config,[input,{...input,scope:'room',scope_id:'deleted'}],['3','4']),/不存在/);
  assert.deepEqual(config,before);
});
