import { test } from 'node:test';
import assert from 'node:assert/strict';
import { catalogChoices, detectHeader, detectMapping, mappedRows, importOperations, matchingChoices } from '../src/features/configuration/quotation/importing/model.ts';
import { cellEdit, editOperations, sheetRows } from '../src/features/configuration/quotation/sheet/model.ts';
const matrix=[['公司抬头'],['名称','型号','数量','单位','单价','产品说明'],['原产品','SAME','2.5','台','','两行\n说明'],['原产品','SAME','1','台','0','']];
const choices=catalogChoices(['windows','国产'].map(id=>({id,name:id,product:{name:'服务器',model:'SAME'},status:'confirmed',source_details:[{id:'s'+id,sheet:'明细',row:8,specification:'原参数',unit:'台'}]})));
const options={choices,evidence:'客户确认原表，含税含运',newId:(()=>{let id=0;return()=>`d${++id}`})()};
function rows(){return mappedRows(matrix,detectHeader(matrix),detectMapping(matrix[1])).map(row=>({...row,kind:'hardware',choice:choices[0].key}));}
test('header mapping retains first detail and supports headerless manual mapping',()=>{
 assert.equal(detectHeader(matrix),1);
 assert.equal(detectHeader([['产品','SAME','1']]),-1);
 assert.equal(mappedRows([['产品','SAME','1']],-1,{model:1,quantity:2})[0].sourceRow,1);
 assert.equal(rows()[0].sourceRow,3);
 assert.equal(rows()[0].description,'两行\n说明');
});
test('same model variants require explicit choice; duplicate rows produce independent devices',()=>{
 assert.equal(matchingChoices(rows()[0],choices).length,2);
 assert.throws(()=>importOperations([{...rows()[0],choice:''}],options),/确认具体/);
 assert.throws(()=>importOperations([{...rows()[0],kind:''}],options),/请选择硬件/);
 const ops=importOperations(rows(),options), devices=ops.filter(o=>o.action==='device_put');
 assert.equal(new Set(devices.map(o=>o.value.id)).size,2);
 assert.equal(devices[0].value.quantity,'2.5');
 assert.equal(ops.filter(o=>o.action==='price_set')[0].value.unit_price,null);
 assert.equal(ops.filter(o=>o.action==='price_set')[1].value.unit_price,'0');
 assert.equal(ops.find(o=>o.action==='description_set').text,'两行\n说明');
});
test('invalid numerics, unit mismatch and missing evidence prevent entire batch',()=>{
 for(const quantity of ['0','-1','=1+1','NaN','']) assert.throws(()=>importOperations([{...rows()[0],quantity}],options),/数值/);
 assert.throws(()=>importOperations([{...rows()[0],price:'=SUM(A1:A2)'}],options),/公式/);
 assert.throws(()=>importOperations([{...rows()[0],unit:'套'}],options),/单位/);
 assert.throws(()=>importOperations(rows(),{...options,evidence:''}),/依据/);
});
test('purchase, description and note edits retain stable identity without modifying catalog',()=>{
 const config={devices:[{id:'one',variant_id:'v',source_id:'s',quantity:'4',note:''}],quotation:{}};
 const rows=[{id:'device:one',deviceId:'one',kind:'device',values:[]}];
 const ops=editOperations(config,[cellEdit(rows,1,3,'客户版说明'),cellEdit(rows,1,4,'0'),cellEdit(rows,1,9,'项目备注')],'');
 assert.deepEqual(ops.map(o=>o.action),['description_set','purchase_set','device_patch']);
 assert.equal(ops[1].quantity,'0');assert.equal(config.devices[0].quantity,'4');
 assert.throws(()=>editOperations(config,[cellEdit(rows,1,3,'=1+2')],''),/公式/);
 assert.throws(()=>cellEdit(rows,1,7,'123'),/只读/);
});
test('template section headings propose editable groups, not product records',()=>{
 const data=[['序号','名称','型号','数量'],['无纸化会议系统'],['1','服务端','SERVER','2'],['会议预约'],['2','预约','BOOK','1']];
 const result=mappedRows(data,0,detectMapping(data[0]));
 assert.equal(result[0].include,false);
 assert.equal(result[1].section,'无纸化会议系统');
 assert.equal(result[3].section,'会议预约');
 assert.deepEqual(result[3].raw,['2','预约','BOOK','1']);
});

test('mixed import links existing hardware without adopting spreadsheet quantity or price',()=>{
 const config={devices:[{id:'server',name:'已有',quantity:'1'}],systems:[{id:'system',name:'系统'}],requirements:[]};
 const ops=importOperations([{...rows()[0],choice:'',kind:'',quantity:'999',price:'9999',existingDeviceId:'server',systemId:'system',roleName:'服务器'}],{...options,configuration:config});
 assert.equal(ops.length,1);assert.equal(ops[0].action,'requirement_put');assert.equal(ops[0].value.device_id,'server');
 assert.equal(config.devices[0].quantity,'1');
});
test('import cannot silently replace an occupied role or assign it twice',()=>{
 const config={devices:[],systems:[{id:'system'}],requirements:[{id:'role',system_id:'system',device_id:'other',role:'服务器'}]};
 assert.throws(()=>importOperations([{...rows()[0],systemId:'system',requirementId:'role'}],{...options,configuration:config}),/角色已关联其他设备/);
});
