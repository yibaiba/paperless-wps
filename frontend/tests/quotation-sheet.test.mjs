import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { columns, parseClipboard, pastedEdits, editOperations, sheetRows, isDeviceRow } from '../src/features/configuration/quotation/sheet/model.ts';
import { assertPreviewVersion } from '../src/features/configuration/quotation/sheet/previewVersion.ts';
import { reviewRows, reviseEdit } from '../src/features/configuration/quotation/sheet/batchReview.ts';
const device = (id, name) => ({ id, name, variant_id: 'same', source_id: 'same', quantity: '4', note: '', source_snapshot: { model: 'same-model' } });
const configuration = { devices: [device('z','乙'), device('a','甲')], quotation: { prices: [], sections: {} } };
const line = (id, name) => ({ device_id:id, name, model:'same-model', specification:'完整参数\n第二行', purchase_quantity:'2.5', unknown_quantity:'0', unit:'台', unit_price:'12.345', amount:'30.86', brand:'原始品牌', note:'原备注', issues:[], consumers:[], section:'无纸化会议系统' });
const output = { lines: [line('z','乙'),line('a','甲')],total:'61.72',known_subtotal:'61.72',issues:[] };
const devices = rows => rows.filter(isDeviceRow);

test('ten columns and values match registered company template; quantity means procurement',()=>{
 const metadata=JSON.parse(readFileSync(new URL('../src/features/configuration/quotation/templateMetadata.json',import.meta.url)));
 assert.deepEqual(columns.map(c=>c.title),metadata.columns);
 const rows=sheetRows(configuration,output,'original');
 assert.deepEqual(devices(rows)[0].values,['1','乙','same-model','完整参数\n第二行','2.5','台','12.345','30.86','原始品牌','原备注']);
 assert.equal(rows.filter(r=>r.kind==='section').length,3);
 assert.equal(rows.at(-1).values[7],'61.72');
 assert.deepEqual(sheetRows(configuration,null,'original'),[]);
});
test('sorting retains equipment identity inside template groups',()=>{
 const rows=sheetRows(configuration,output,'name');
 assert.equal(rows[1].deviceId,'a');
 const ops=editOperations(configuration,pastedEdits(rows,{row:2,column:6},'0'),'确认的依据');
 assert.equal(ops[0].value.device_id,'a');
 assert.equal(ops[0].value.unit_price,'0');
 assert.equal(configuration.devices[1].quantity,'4');
});
test('existing-only equipment is excluded; unknown supply is blank, not zero; extra groups retained',()=>{
 const result={...output,total:null,lines:[{...output.lines[0],purchase_quantity:'0',amount:'0.00'},{...output.lines[1],purchase_quantity:'0',unknown_quantity:'2',amount:'0.00',section:'会议预约',issues:['供货待确认']}]};
 const rows=sheetRows(configuration,result,'original');
 assert.equal(devices(rows).length,1);
 assert.equal(devices(rows)[0].values[4],'');
 assert.equal(devices(rows)[0].values[7],'');
 assert.equal(rows.at(-1).values[7],'待确认');
 assert.equal(rows.filter(r=>r.kind==='section').at(-1).values[0],'会议预约');
});
test('rectangular quoted clipboard preserves multiline descriptions',()=>{
 assert.deepEqual(parseClipboard('2\t0\t公共设备\t"两行\r\n含""引号"""\r\n'),[['2','0','公共设备','两行\r\n含"引号"']]);
 assert.throws(()=>parseClipboard('"unfinished'),/未闭合/);
});
test('batch prices preserve decimal text, zero and common evidence',()=>{
 const rows=sheetRows(configuration,output,'original');
 const edits=pastedEdits(rows,{row:2,column:6},'0\n12.34567890123456789');
 const ops=editOperations(configuration,edits,'确认的测试依据');
 assert.equal(ops[0].value.unit_price,'0');
 assert.equal(ops[1].value.unit_price,'12.34567890123456789');
 assert.throws(()=>editOperations(configuration,edits,''),/依据/);
});
test('readonly calculated cells, section rows, formulas and partial paste reject atomically',()=>{
 const rows=sheetRows(configuration,output,'original');
 assert.equal(editOperations(configuration,pastedEdits(rows,{row:2,column:4},'2'),'')[0].action,'purchase_set');
 assert.throws(()=>pastedEdits(rows,{row:1,column:6},'2'),/G2/);
 assert.throws(()=>pastedEdits(rows,{row:2,column:6},'8\t9'),/H3/);
 for(const value of ['','-1','=1+1','NaN']) assert.throws(()=>editOperations(configuration,pastedEdits(rows,{row:2,column:6},value),'依据'),/G3/);
});
test('checked zero price differs from missing; stale output stays internally consistent',()=>{
 const result={...output,lines:[{...output.lines[0],unit_price:'0',amount:'0.00'},{...output.lines[1],unit_price:null,amount:null,issues:['缺价']}]};
 const rows=devices(sheetRows(configuration,result,'original'));
 assert.equal(rows[0].values[6],'0');assert.equal(rows[1].values[6],'');
 assert.equal(rows[1].values[7],'');assert.equal(rows[1].values[9],'原备注');
 const changed={...configuration,devices:configuration.devices.map(d=>({...d,name:'新产品',variant_id:'changed'}))};
 assert.equal(devices(sheetRows(changed,result,'original'))[0].values[1],'乙');
});
test('batch review resolves source values by ID after sorting and supports correction',()=>{
 const rows=sheetRows(configuration,output,'name');
 const edits=pastedEdits(rows,{row:2,column:6},'0\n12.5');
 const reviewed=reviewRows(edits,rows);
 assert.equal(reviewed[0].name,'甲');assert.equal(reviewed[0].model,'same-model');assert.equal(reviewed[0].previous,'12.345');
 const revised=reviseEdit(edits,{...edits[1],value:'3.25'});
 assert.equal(editOperations(configuration,revised,'依据')[1].value.unit_price,'3.25');
 assert.equal(edits[1].value,'12.5');
 assert.equal(reviewRows([{...edits[0],deviceId:'deleted'}],rows)[0].name,'设备已移除');
});
test('late response cannot overwrite newer edits, undo, saved revision or changed evidence',()=>{
 const started={draft:4,project:2,generation:0};
 assert.doesNotThrow(()=>assertPreviewVersion(started,{...started},4));
 for(const key of ['draft','project','generation']) assert.throws(()=>assertPreviewVersion(started,{...started,[key]:started[key]+1},4),/过期/);
 assert.throws(()=>assertPreviewVersion(started,started,3),/过期/);
});
test('a business device ID cannot collide with generated template rows',()=>{
 const id='section:无纸化会议系统';
 const c={...configuration,devices:[device(id,'同名标识设备')]};
 const rows=sheetRows(c,{...output,lines:[line(id,'同名标识设备')]},'original');
 assert.equal(new Set(rows.map(r=>r.id)).size,rows.length);
 assert.equal(pastedEdits(rows,{row:2,column:6},'1')[0].deviceId,id);
});
