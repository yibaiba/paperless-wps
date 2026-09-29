import test from 'node:test';
import assert from 'node:assert/strict';
import { priceDefaults, variantPayload, defaultAction, priceDecisions } from '../src/features/configuration/catalog/updates/types.ts';
test('reopening a partial price decision restores six columns without inventing amounts', () => {
 const value = [{ column: '甲方指导价', state: 'amount', amount: '0', effective_date: '2027-01-01' }];
 const actual = priceDefaults(value, '2026-09-29');
 assert.equal(actual.length, 6);
 assert.deepEqual(actual.find(p => p.column === '甲方指导价'), value[0]);
 assert.equal(actual.filter(p => p.state === 'skip' && p.amount === null).length, 5);
 assert.equal(value.length, 1);
});
test('configuration edit preserves non-owned facts and excludes derived source payload', () => {
 const value = { product_id: 'p', name:'配置', status:'confirmed', source_ids:['source'], product:{}, revision:9,
   included_items:[{id:'included',status:'draft'}], replacements:['other'], review_requirements:[{id:'rule',revision:2}], attributes:[] };
 const result = variantPayload(value);
 assert.deepEqual(result.included_items,value.included_items);
 assert.deepEqual(result.review_requirements,value.review_requirements);
 assert.equal('source_ids' in result,false);
 assert.equal('revision' in result,false);
});

test('candidate-specific specification changes default to an independent configuration', () => {
 assert.equal(defaultAction('specification'), 'new_variant');
 assert.equal(defaultAction('new'), 'new_product');
 assert.equal(defaultAction('prices'), 'prices');
});

test('form values retain controlled price columns even when noneditable columns are not registered', () => {
 const values = priceDefaults([], '2026-09-29').map(({column, ...editable}) => editable);
 values[0] = {state:'amount', amount:'0',effective_date:'2026-09-29'};
 const result = priceDecisions(values);
 assert.equal(result[0].column,'出厂指导价');
 assert.equal(result[0].amount,'0');
 assert.equal(result[5].column,'最低客户报价');
 assert.equal(result[5].amount,null);
});
