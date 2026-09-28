import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyProjection, diffProjection, initialProjection, snapshotRows } from '../src/features/configuration/quotation/sheet/projection.ts';
const layout = { titles: ['名称','型号','数量'], minimumRows: 30 };
const row = (id, quantity = '1') => ({id, values: [id, 'same-model', quantity]});

test('initial projection contains one header and the exact source text', () => {
  const plan = initialProjection([row('a','0.1234567890123456789')], layout);
  assert.equal(plan.rowCount, 30);
  assert.equal(plan.cellCount, 6);
  assert.deepEqual(plan.cells[1][2], {value:'0.1234567890123456789',style:'body'});
  assert.equal(plan.cells[0][0].style,'header');
});
test('500-row single edit changes one cell and equal data performs no writes', () => {
  const before = Array.from({length:500},(_,i)=>row(String(i)));
  const after = before.map((r,i)=>i===250?row(r.id,'2.5'):r);
  const plan=diffProjection(before,after,layout);
  assert.equal(plan.cellCount,1);
  assert.equal(plan.resized,false);
  assert.deepEqual(plan.cells,{251:{2:{value:'2.5',style:null}}});
  const calls=[];
  applyProjection(diffProjection(after,snapshotRows(after),layout),{resize:()=>{calls.push('resize');return true},write:()=>{calls.push('write');return true}});
  assert.deepEqual(calls,[]);
});
test('sorting same-model devices updates positions, not identities',()=>{
  const rows=[row('a','1'),row('b','2')];
  const plan=diffProjection(rows,[rows[1],rows[0]],layout);
  assert.equal(plan.reordered,true);
  assert.equal(plan.cellCount,6);
  assert.equal(plan.cells[1][0].value,'b');
  assert.equal(plan.cells[1][2].value,'2');
});
test('deletion clears remaining trailing cells and never writes outside resized sheet',()=>{
  const before=[row('a'),row('b'),row('c')];
  const plan=diffProjection(before,[before[0],before[2]],layout);
  assert.equal(plan.cells[2][0].value,'c');
  assert.equal(plan.cells[3][0].value,'');
  assert.equal(plan.cells[3][2].value,'');
  const shrink=diffProjection(Array.from({length:500},(_,i)=>row(String(i))),[row('0')],layout);
  assert.equal(shrink.rowCount,30);
  assert.equal(shrink.resized,true);
  assert.equal(Math.max(...Object.keys(shrink.cells).map(Number)),29);
  const cleared=diffProjection(before,[],layout);
  assert.equal(cleared.cellCount,9);
  assert.equal(cleared.cells[1][0].value,'');
});
test('new rows get styles and crossing the minimum row count resizes once',()=>{
  const before=Array.from({length:29},(_,i)=>row(String(i)));
  const plan=diffProjection(before,[...before,row('new')],layout);
  const calls=[];
  applyProjection(plan,{resize:(count)=>{calls.push(['resize',count]);return true},write:(cells)=>{calls.push(['write',cells]);return true}});
  assert.equal(plan.rowCount,31);
  assert.equal(calls.length,2);
  assert.equal(plan.cells[30][0].style,'body');
});
test('failed resize or cell command throws and does not mutate source snapshots',()=>{
  const rows=[row('a')], saved=snapshotRows(rows);
  rows[0].values[2]='7';
  assert.equal(saved[0].values[2],'1');
  const plan=diffProjection(saved,rows,layout);
  assert.throws(()=>applyProjection(plan,{resize:()=>true,write:()=>false}),/单元格更新/);
  let writes=0;
  assert.throws(()=>applyProjection({...plan,resized:true},{resize:()=>false,write:()=>{writes++;return true}}),/行数调整/);
  assert.equal(writes,0);
  assert.equal(saved[0].values[2],'1');
});
test('template sections regain their style after insert/delete and unchanged price stays sparse',()=>{
 const section={id:'section:a',kind:'section',values:['无纸化','','']};
 const before=[section,{...row('a'),kind:'device'}];
 const after=[{...row('b'),kind:'device'},section,{...row('a'),kind:'device'}];
 const plan=diffProjection(before,after,layout);
 assert.equal(plan.cells[1][0].style,'body');
 assert.equal(plan.cells[2][0].style,'section');
 assert.equal(snapshotRows(after)[1].kind,'section');
 assert.equal(diffProjection(after,snapshotRows(after),layout).cellCount,0);
});

import { rowLayout } from '../src/features/configuration/quotation/sheet/templateLayout.ts';
test('section merges and row heights move with template rows; total never merges the amount cell',()=>{
 const rows=[{id:'s',kind:'section',values:[]},row('a'),{id:'total',kind:'total',values:[]}];
 const layout=rowLayout(rows);
 assert.deepEqual(layout.mergeData,[{startRow:1,endRow:1,startColumn:0,endColumn:9},{startRow:3,endRow:3,startColumn:0,endColumn:6}]);
 assert.equal(layout.rowData[1].h,32);assert.equal(layout.rowData[2].h,92);
 assert.ok(Object.values(layout.rowData).every(data=>data.ia===0),'fixed template rows must ignore SDK automatic height caches');
 assert.equal(rowLayout([row('a'),...rows]).mergeData[0].startRow,2);
});
