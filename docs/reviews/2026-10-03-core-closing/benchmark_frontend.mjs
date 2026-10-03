import { performance } from 'node:perf_hooks';
import { writeFileSync } from 'node:fs';
import { diffProjection, applyProjection } from '../../../frontend/src/features/configuration/quotation/sheet/projection.ts';
const median = values => [...values].sort((a,b)=>a-b)[Math.floor(values.length/2)];
const results = [100,500].map(size => {
 const layout={titles:Array.from({length:10},(_,i)=>String(i)),minimumRows:30};
 const rows=Array.from({length:size},(_,i)=>({id:String(i),values:Array.from({length:10},(_,c)=>c===0?String(i):'value')}));
 const changed=rows.map((r,i)=>i===Math.floor(size/2)?{...r,values:r.values.map((v,c)=>c===9?'edited':v)}:r);
 const samples=[];let cells=0,writes=0;
 for(let i=0;i<101;i++) {const start=performance.now();const diff=diffProjection(rows,changed,layout);samples.push(performance.now()-start);cells=diff.cellCount;}
 applyProjection(diffProjection(rows,changed,layout),{resize:()=>true,write:()=>{writes++;return true;}});
 let unchanged=0;applyProjection(diffProjection(rows,rows,layout),{resize:()=>true,write:()=>{unchanged++;return true;}});
 if(cells!==1||writes!==1||unchanged!==0)throw new Error('incremental projection regression');
 return {rows:size,median_projection_ms:median(samples.slice(1)),writes,cells,unchanged_writes:unchanged};
});
writeFileSync(new URL('./frontend-projection-performance.json',import.meta.url),JSON.stringify(results,null,2));
console.log(results);
