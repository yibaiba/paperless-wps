import test from 'node:test';
import assert from 'node:assert/strict';
import { visibleSegments } from '../src/features/configuration/materials/segments.ts';
test('merged source text appears once without losing the selected cell reference', () => {
 const segments = [{ id:'a', location:'说明!B2', anchor:'A1', text:'共用条件' }, { id:'b', location:'说明!C2', anchor:'A1', text:'共用条件' }, { id:'c', location:'说明!D2', anchor:'D2', text:'=SUM(A1:A2)' }];
 assert.deepEqual(visibleSegments(segments,''), [segments[0],segments[2]]);
 assert.equal(visibleSegments(segments,'B2')[0].id,'a');
 assert.equal(visibleSegments(segments,'SUM')[0].text,'=SUM(A1:A2)');
 assert.equal(segments.length,3);
});
