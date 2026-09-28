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
