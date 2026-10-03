import { test } from 'node:test';
import assert from 'node:assert/strict';
import { configurationOperations } from '../src/features/configuration/projects/drafts/operations.ts';
import { applyProjectionPatch } from '../src/features/configuration/projects/drafts/projectionPatch.ts';
const base={actor:'人',evidence:'依据',rooms:[],systems:[],requirements:[],devices:[{id:'a',name:'服务器',quantity:'1',note:'',source_id:'s',variant_id:'v',source_snapshot:{id:'s'},variant_snapshot:{id:'v',revision:1,product:{id:'p',revision:1}}}],accessory_allocations:[],supply_allocations:[],accessory_choices:[],drawing_xml:''};
test('notes generate only a device patch; unchanged data produces no operations',()=>{
 assert.deepEqual(configurationOperations(base,base),[]);
 const next=structuredClone(base);next.devices[0].note='changed';
 assert.deepEqual(configurationOperations(base,next),[{action:'device_patch',device_id:'a',note:'changed'}]);
 assert.equal(base.devices[0].note,'');
});
test('device replacement never submits snapshots',()=>{
 const next=structuredClone(base);next.devices[0].variant_id='other';
 const [operation]=configurationOperations(base,next);
 assert.equal(operation.action,'device_put');assert.equal('variant_snapshot' in operation.value,false);
});
test('sparse nested projection preserves unmodified identities, truncates rows and supports null',()=>{
 const before={lines:[{id:'a',note:''},{id:'b',note:'old'}],total:'10',stale:true};
 const result=applyProjectionPatch(before,{fields:{lines:{items:{1:{fields:{note:{value:'new'}},removed:[]}},length:2},total:{value:null}},removed:['stale']});
 assert.equal(result.lines[0],before.lines[0]);assert.equal(result.lines[1].note,'new');assert.equal(result.total,null);assert.equal('stale' in result,false);
 assert.equal(before.lines[1].note,'old');assert.equal(applyProjectionPatch(result.lines,{items:{},length:1}).length,1);
});

test('included credit uses shared operations and preserves device identity', () => {
 const allocation={id:'credit',demand_id:'need',device_id:'a',included_item_id:'bundled',host_variant_id:'v',host_variant_revision:1,quantity:'1',evidence:'依据'};
 const next={...base,included_allocations:[allocation]};
 assert.deepEqual(configurationOperations(base,next),[{action:'included_link',value:allocation}]);
 assert.deepEqual(configurationOperations(next,base),[{action:'included_remove',allocation_id:'credit'}]);
 assert.deepEqual(configurationOperations(next,{...base,devices:[]}),[{action:'remove',collection:'devices',id:'a'}]);
 assert.deepEqual(configurationOperations(next,next),[]);
});

test('feature-only confirmation persists as a business operation and undo clears it', () => {
 const before = { ...base, systems: [{ id: 's', name: '隔离' }], generation: { features_confirmed: [], sources: [{ id: 'keep' }] } };
 const after = { ...before, generation: { ...before.generation, features_confirmed: ['s'] } };
 assert.deepEqual(configurationOperations(before, after), [{ action: 'system_setup', system: before.systems[0], features_confirmed: true }]);
 assert.deepEqual(configurationOperations(after, before), [{ action: 'system_setup', system: before.systems[0], features_confirmed: false }]);
 assert.deepEqual(configurationOperations(after, after), []);
});

test('scope-only input edits persist without changing generation preferences', () => {
 const before = { ...base, rooms: [{ id: 'r', name: '会议室' }], room_inputs: {}, project_inputs: [], generation: { features_confirmed: [], preferences: [{ requirement_id: 'keep' }] } };
 const inputs = [{ key: 'count', kind: 'number', value: '3', unit: '' }];
 const after = { ...before, room_inputs: { r: inputs }, project_inputs: inputs };
 assert.deepEqual(configurationOperations(before, after), [{ action: 'requirements_patch', room_inputs: { r: inputs }, project_inputs: inputs }]);
 assert.deepEqual(configurationOperations(after, before), [{ action: 'requirements_patch', room_inputs: {}, project_inputs: [] }]);
 assert.deepEqual(configurationOperations(after, after), []);
});

test('decision upgrade is explicit and keeps product and price refresh separate', () => {
 const before = {...base, decision_runtime:'python-v3'};
 const after = {...base, decision_runtime:'zen-v1', decision_bundle_id:'compiled-version'};
 assert.deepEqual(configurationOperations(before, after), [{action:'decision_upgrade', expected_bundle_id:'compiled-version'}]);
 assert.throws(() => configurationOperations(before, {...after, decision_bundle_id:null}), /预览决策升级/);
});
