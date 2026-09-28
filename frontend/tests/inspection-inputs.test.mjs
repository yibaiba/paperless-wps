import { test } from 'node:test';
import assert from 'node:assert/strict';
import { systemMetrics, initialInputs, combineInputs } from '../src/features/configuration/projects/forms/inspectionInputs.ts';
const metric = {input_key:'terminals',input_unit:'台'};
test('only instantiated roles contribute input fields, preserving their pinned revision',()=>{
 const definitions={packages:[],definitions:[{id:'d',roles:[{id:'active',inspection_profile:{id:'p',revision:1}},{id:'optional',inspection_profile:{id:'q',revision:1}}],inspection_profiles:[{id:'p',revision:1,metrics:[metric]},{id:'p',revision:2,metrics:[{input_key:'new'}]},{id:'q',revision:1,metrics:[{input_key:'optional'}]}]}]};
 assert.deepEqual(systemMetrics({id:'s',definition_id:'d'},{requirements:[{system_id:'s',role_id:'active'}]},definitions),[metric]);
});
test('historical units are not relabelled as a new unit without explicit input',()=>{
 const original=[{key:'terminals',kind:'quantity',value:'2',unit:'个'},{key:'custom',kind:'text',value:'kept',unit:''}];
 const values=initialInputs(original,[metric]);
 assert.equal(values.values.terminals,null);assert.equal(values.extra[0].key,'custom');
 assert.equal(original[0].unit,'个');assert.equal(original[0].value,'2');
});
test('duplicate custom inputs are rejected rather than silently discarded',()=>{
 assert.throws(()=>combineInputs([metric],{terminals:'32'},[{key:'terminals',value:'48'}]),/重复/);
 const value=combineInputs([metric],{terminals:'0'},[{key:'custom',kind:'text',value:'keep',unit:''}]);
 assert.equal(value[0].value,'0');assert.equal(value[1].value,'keep');
});
