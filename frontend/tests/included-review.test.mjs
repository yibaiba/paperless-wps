import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reviewIncludedAllocation } from '../src/features/configuration/projects/includedReview.ts';
import { configurationOperations } from '../src/features/configuration/projects/drafts/operations.ts';
const credit={id:'credit',demand_id:'need',device_id:'host',included_item_id:'part',host_variant_id:'v',host_variant_revision:1,quantity:'1',evidence:'old'};
const base={actor:'人',evidence:'依据',rooms:[],systems:[],requirements:[],devices:[{id:'host',variant_id:'v',quantity:'1'}],accessory_allocations:[],included_allocations:[credit],drawing_xml:''};
const offer={device_id:'host',included_item_id:'part',host_variant_id:'v',host_variant_revision:2};
test('review emits one atomic remove/link batch, exact decimal text, same allocation ID',()=>{
 const next=reviewIncludedAllocation(base,{allocation:credit,offer,quantity:'0.1234567890123456789',evidence:' new basis '});
 const value={...credit,host_variant_revision:2,quantity:'0.1234567890123456789',evidence:'new basis'};
 assert.deepEqual(configurationOperations(base,next),[{action:'included_remove',allocation_id:'credit'},{action:'included_link',value}]);
 assert.equal(base.included_allocations[0],credit);assert.equal(credit.host_variant_revision,1);
 assert.equal(next.devices,base.devices);
});
test('deleted allocations and unrelated host/items cannot be silently recreated',()=>{
 assert.throws(()=>reviewIncludedAllocation({...base,included_allocations:[]},{allocation:credit,offer,quantity:'1',evidence:'x'}),/原抵扣/);
 assert.throws(()=>reviewIncludedAllocation(base,{allocation:credit,offer:{...offer,device_id:'other'},quantity:'1',evidence:'x'}),/原宿主/);
});
