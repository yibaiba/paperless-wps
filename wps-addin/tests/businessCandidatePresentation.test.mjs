import test from 'node:test';
import assert from 'node:assert/strict';
import { businessCandidatePresentation } from '../src/businessCandidatePresentation.ts';

function candidate(id, configuration, source) {
  return { label: '配置选择', patches: [{ sheet: '报价表', row: 4, column: 2, after: '红盾设备' }],
    line_bindings: [{ device_id: id, variant_id: `variant-${id}`, source_id: `source-${id}`,
      sheet: '报价表', row: 4, confirmed_values: { name: '红盾设备' } }],
    changes: [{ kind: 'devices', after: { id, variant_snapshot: configuration, source_snapshot: source } }] };
}

test('same-name candidates expose actual variant and source details, not their rank', () => {
  const a = businessCandidatePresentation(candidate('A', { name: '标准版', description: '32 GB' },
    { sheet: '硬件', row: 12, import_id: 'batch-1' }), 2);
  const b = businessCandidatePresentation(candidate('B', { name: '扩展版', description: '64 GB' },
    { sheet: '硬件', row: 19, import_id: 'batch-2' }), 2);
  assert.equal(a.title, b.title);
  assert.equal(a.configuration, '标准版 · 32 GB');
  assert.equal(b.configuration, '扩展版 · 64 GB');
  assert.equal(a.source, '硬件 · 第 12 行 · 批次 batch-1');
  assert.equal(b.source, '硬件 · 第 19 行 · 批次 batch-2');
  assert.equal(b.identity, '配置 ID variant-B · 来源 ID source-B');
  assert.equal(b.location, '报价表 · 第 4 行');
});

test('missing or malformed snapshots identify missing details and keep concrete IDs', () => {
  for (const snapshot of [null, [], 'bad', { name: {}, description: [], sheet: {}, row: -1 }]) {
    const copy = businessCandidatePresentation(candidate('B', snapshot, snapshot), 2);
    assert.equal(copy.configuration, '未提供配置说明 · 配置 ID variant-B');
    assert.equal(copy.source, '未提供来源位置 · 来源 ID source-B');
    assert.doesNotMatch(Object.values(copy).join(' '), /\[object Object\]/);
  }
});

test('group candidate details follow the target device, not an unrelated snapshot', () => {
  const item = candidate('B', { name: '目标配置' }, { sheet: '目标来源' });
  item.changes.unshift({ kind: 'devices', after: { id: 'other', variant_snapshot: { name: '无关配置' } } });
  item.changes.unshift({ kind: 'requirements', after: { id: 'B', variant_snapshot: { name: '非产品变更' } } });
  item.line_bindings.unshift({ ...item.line_bindings[0], device_id: 'other', row: 6 });
  assert.equal(businessCandidatePresentation(item, 2).configuration, '目标配置');
});

test('relationship-only suggestions retain their business label without fabricated sources', () => {
  assert.deepEqual(businessCandidatePresentation({ label: '关联现有设备', patches: [], line_bindings: [], changes: [] }, 2),
    { title: '关联现有设备', location: '用途关联', configuration: '关联现有设备', source: '', identity: '' });
});
