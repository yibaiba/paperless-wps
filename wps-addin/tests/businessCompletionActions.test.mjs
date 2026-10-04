import test from 'node:test';
import assert from 'node:assert/strict';
import { applyBusinessCompletion, AppliedCompletionRefreshError, resolveBusinessChoice,
  undoBusinessCompletion, UndoneCompletionRefreshError } from '../src/businessCompletionActions.ts';
import { LatestRequest } from '../src/latestRequest.ts';

function fixture() {
  let metadata = { line_bindings: [], business: { local_revision: 0, operations: [], recent_edits: [] } };
  let value = '旧值';
  const journals = new Map();
  const host = {
    workbookKey: () => 'test.xlsx', businessRevision: () => metadata.business.local_revision,
    inlineContext: () => ({ session_id: 'original-cell' }),
    readCell: (cell) => ({ ...cell, value, formula: '', merged: false }),
    writeCellValue: (_, next) => { value = next; },
    readMetadata: () => metadata, writeMetadata: (next) => { metadata = next; },
    journals: () => [...journals.values()], writeJournal: (journal) => journals.set(journal.operation_id, journal),
  };
  const suggestion = { id: 'edit', local_revision: 0, applicable: true, line_bindings: [], business_operations: [],
    patches: [{ sheet: '测试', row: 2, column: 1, before: '旧值', after: '新值' }] };
  return { host, suggestion, operationId: 'operation', context: { workbook_key: 'test.xlsx', session_id: 'original-cell' } };
}

test('refresh failure reports a committed edit and a second delivery cannot rewrite it', () => {
  const f = fixture();
  const afterApply = () => { throw new Error('宿主读行失败'); };
  for (let i = 0; i < 2; i++) {
    assert.throws(() => applyBusinessCompletion({ ...f, afterApply }), (error) =>
      error instanceof AppliedCompletionRefreshError && /已写入.*宿主读行失败/.test(error.message));
  }
  assert.equal(f.host.readCell({}).value, '新值');
  assert.equal(f.host.businessRevision(), 1);
  assert.equal(f.host.journals()[0].state, 'applied');
});

test('write failure keeps the actual recovery error and does not run follow-up refresh', () => {
  const f = fixture(); let refreshed = false;
  f.host.writeCellValue = () => { throw new Error('写入被拒绝'); };
  assert.throws(() => applyBusinessCompletion({ ...f, afterApply: () => { refreshed = true; } }), (error) =>
    !(error instanceof AppliedCompletionRefreshError) && /写入失败/.test(error.message));
  assert.equal(refreshed, false);
  assert.equal(f.host.readCell({}).value, '旧值');
});

test('undo is durable even if refreshing rows fails, and a repeated delivery cannot undo twice', () => {
  const f = fixture();
  applyBusinessCompletion({ ...f, afterApply() {} });
  const journal = f.host.journals()[0];
  const afterUndo = () => { throw new Error('宿主读行失败'); };
  for (let i = 0; i < 2; i++) {
    assert.throws(() => undoBusinessCompletion({ host: f.host, journal, afterUndo }), (error) =>
      error instanceof UndoneCompletionRefreshError && /已撤销.*宿主读行失败/.test(error.message));
  }
  assert.equal(f.host.readCell({}).value, '旧值');
  assert.equal(f.host.businessRevision(), 2);
  assert.equal(f.host.journals()[0].state, 'undone');
  assert.equal(f.host.readMetadata().business.recent_edits.filter((edit) => edit.kind === 'undo').length, 1);
});

test('undo conflict remains a real failure and never refreshes as though it succeeded', () => {
  const f = fixture(); let refreshed = false;
  applyBusinessCompletion({ ...f, afterApply() {} });
  f.host.writeCellValue({}, '手工修改');
  assert.throws(() => undoBusinessCompletion({ host: f.host, journal: f.host.journals()[0],
    afterUndo() { refreshed = true; } }), /已被修改/);
  assert.equal(refreshed, false);
  assert.equal(f.host.readCell({}).value, '手工修改');
  assert.equal(f.host.journals()[0].state, 'applied');
});

test('explicit selection uses the cancellation signal and cannot revive an old query', async () => {
  const f = fixture(), latest = new LatestRequest(), pending = Promise.withResolvers();
  const request = latest.begin();
  const selected = resolveBusinessChoice({ ...f, request, load: (signal) => {
    assert.equal(signal, request.signal); return pending.promise;
  } });
  latest.cancel(); pending.resolve({ items: [], local_revision: 0 });
  assert.equal(await selected, undefined);
});

test('explicit choice exposes changed workbooks, stale revisions and real network failures', async () => {
  const f = fixture(), latest = new LatestRequest();
  await assert.rejects(resolveBusinessChoice({ ...f, request: latest.begin(),
    load: async () => { throw new Error('离线'); } }), /离线/);
  await assert.rejects(resolveBusinessChoice({ ...f, request: latest.begin(),
    load: async () => ({ local_revision: 8 }) }), /工作簿已变化/);
  await assert.rejects(resolveBusinessChoice({ ...f, request: latest.begin(), load: async () => {
    f.host.workbookKey = () => 'copy.xlsx'; return { local_revision: 0 };
  } }), /工作簿或项目绑定/);
});

test('selection response cannot apply between a host cell switch and React effect cleanup', async () => {
  for (const current of [null, { session_id: 'different-cell' }]) {
    const f = fixture(), latest = new LatestRequest(), pending = Promise.withResolvers();
    const selected = resolveBusinessChoice({ ...f, request: latest.begin(), load: () => pending.promise });
    f.host.inlineContext = () => current;
    pending.resolve({ local_revision: 0 });
    await assert.rejects(selected, /补全单元格已切换/);
    assert.equal(f.host.journals().length, 0);
  }
});
