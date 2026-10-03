import assert from 'node:assert/strict';
import { test } from 'node:test';
import { nextEditAction } from '../src/nextEditState.ts';
import { WorkbookRowIndex } from '../src/workbookRowIndex.ts';
import { subscribeHostEvent, sheetChange } from '../src/hostEvents.ts';
import { recoverSyncReceipt } from '../src/syncRecovery.ts';
import { deviceIdForLine } from '../src/businessIdentity.ts';
import { BusinessPrefetch, businessPrefetchKey } from '../src/businessPrefetch.ts';
import { ambiguousStructuralIdentities, scanWorkbook } from '../src/workbook.ts';
import { completionRequest } from '../src/businessWorkbook.ts';
import { handleInlineTab, returnNativeTab } from '../src/nativeTab.ts';
import { assertWorkbookSession, captureWorkbookSession, inWorkbookSession, writeInlineInput } from '../src/workbookSession.ts';
import { LatestRequest } from '../src/latestRequest.ts';
import { applyCandidate } from '../src/candidateAcceptance.ts';

const base = { cell: { sheet: 'quote', row: 3 }, ready: true, composing: false, explicit: false, count: 1,
  suggestion: { patches: [{ sheet: 'quote', row: 3 }], applicable: true, acceptance: 'inline' } };

test('copied bindings cannot receive an asynchronous receipt intended for another file', () => {
  let filename = '/quotes/original.xlsx';
  const metadata = { workbook_instance_id: 'copied', binding: { binding_id: 'same-binding' }, pending_sync: { operation_id: 'pending' } };
  const host = { workbookKey: () => filename, readMetadata: () => metadata };
  const session = captureWorkbookSession(host);
  filename = '/quotes/copy.xlsx';
  assert.throws(() => assertWorkbookSession(host, session), /工作簿或项目绑定已切换/);
  assert.equal(metadata.pending_sync.operation_id, 'pending');
  filename = '/quotes/original.xlsx';
  assert.doesNotThrow(() => assertWorkbookSession(host, session));
  metadata.binding.binding_id = 'rebound';
  assert.throws(() => assertWorkbookSession(host, session), /项目绑定/);
});

test('legacy late response and acceptance cannot write to a switched workbook', async () => {
  let filename = 'A.xlsx'; let writes = 0; const candidates = [];
  const host = { workbookKey: () => filename, readMetadata: () => ({ schema_version: 1 }),
    writeCandidate: () => { writes++; }, writeMetadata: () => { writes++; } };
  const session = captureWorkbookSession(host);
  const latest = new LatestRequest(); const request = latest.begin();
  const transport = Promise.withResolvers();
  const pending = transport.promise.then((items) => {
    if (request.isCurrent()) inWorkbookSession(host, { session, run: () => candidates.push(...items) });
  });
  // App's WorkbookActivate cancels the request and invalidates its candidate session synchronously.
  filename = 'B.xlsx'; latest.cancel();
  transport.resolve([{ key: 'old-candidate' }]); await pending;
  assert.deepEqual(candidates, []);
  assert.throws(() => inWorkbookSession(host, { session, run: () => applyCandidate({
    host, cell: { row: 8 }, profile: { sheet_selector: 'A' }, candidate: {}, metadata: {},
  }) }), /工作簿或项目绑定/);
  assert.equal(writes, 0);
});

test('inline input handler rejects a stale file or project binding before writing', () => {
  let filename = 'A.xlsx', bindingId = 'binding-A'; const writes = [];
  const host = { workbookKey: () => filename,
    readMetadata: () => ({ binding: { binding_id: bindingId } }),
    writeCellValue: (cell, value) => writes.push([cell, value]) };
  const context = { workbook_key: filename, binding_id: bindingId, cell: { row: 4, column: 2 } };
  filename = 'B.xlsx';
  assert.throws(() => writeInlineInput({ host, context, value: '软件' }), /工作簿或项目绑定/);
  filename = 'A.xlsx'; bindingId = 'binding-B';
  assert.throws(() => writeInlineInput({ host, context, value: '软件' }), /工作簿或项目绑定/);
  assert.equal(writes.length, 0);
  bindingId = 'binding-A'; writeInlineInput({ host, context, value: '软件' });
  assert.deepEqual(writes, [[context.cell, '软件']]);
});
test('next edit locates offscreen changes and requires preview for quantities', () => {
  assert.equal(nextEditAction(base), 'apply');
  assert.equal(nextEditAction({ ...base, composing: true }), 'native');
  assert.equal(nextEditAction({ ...base, ready: false }), 'native');
  assert.equal(nextEditAction({ ...base, count: 2 }), 'expand');
  assert.equal(nextEditAction({ ...base, cell: { sheet: 'quote', row: 9 } }), 'locate');
  assert.equal(nextEditAction({ ...base, suggestion: { ...base.suggestion, acceptance: 'preview' } }), 'preview');
});

test('row index reads once and refreshes only affected rows, structural edits rebuild', () => {
  let reads = 0; const rows = [];
  const host = { readRows: () => { reads++; return [{ row: 3, values: { model: 'a' } }]; },
    readRow: (_, row) => { rows.push(row); return { row, values: { model: 'changed' } }; } };
  const index = new WorkbookRowIndex(host, { sheet_selector: 'quote' });
  index.read(); index.read(); index.changed({ sheet: 'other', row: 3, rowCount: 1 });
  index.changed({ sheet: 'quote', row: 3, rowCount: 1 }); index.read();
  assert.equal(reads, 1); assert.deepEqual(rows, [3]);
  index.changed({ sheet: 'quote', structural: true }); index.read(); assert.equal(reads, 2);
});

test('host listeners share registration and preserve sheet/range information', () => {
  const handlers = new Map(); let adds = 0, removes = 0, calls = 0;
  const api = { AddApiEventListener: (name, fn) => { adds++; handlers.set(name, fn); },
    RemoveApiEventListener: () => { removes++; } };
  const stop1 = subscribeHostEvent(api, 'SheetChange', () => calls++);
  const stop2 = subscribeHostEvent(api, 'SheetChange', () => calls++);
  handlers.get('SheetChange')(); assert.equal(adds, 1); assert.equal(calls, 2);
  stop1(); assert.equal(removes, 0); stop2(); assert.equal(removes, 1);
  assert.equal(sheetChange({ Name: 'quote' }, { Row: 3, Address: '$3:$3' }).structural, true);
});

test('sync recovery preserves later edits and consumes only submitted business operations', () => {
  const op = { action: 'requirement_put' };
  const metadata = { binding: { binding_id: 'binding' }, line_bindings: [{ line_id: 'row', requirement_id: 'role' }],
    business: { local_revision: 1, operations: [op, { action: 'later' }] },
    pending_sync: { operations: [op], line_bindings: [] } };
  const result = recoverSyncReceipt(metadata, { binding_id: 'binding', base_revision: 4, line_bindings: [{ line_id: 'row', device_id: 'device' }] });
  assert.equal(result.line_bindings[0].requirement_id, 'role');
  assert.deepEqual(result.business.operations, [{ action: 'later' }]);
  assert.equal(result.pending_sync, undefined);
  assert.throws(() => recoverSyncReceipt({ ...metadata, business: { operations: [] } }, { binding_id: 'binding' }), /重排/);
});

test('workbook device identity uses RFC UUID v5 consistently', async () => {
  assert.equal(await deviceIdForLine('binding', 'line'), '6145a2fa-349c-5212-8973-444e41d12ab2');
});

test('business prefetch rejects stale versions, shares one request and exposes failure', async () => {
  const options = { context: { workbook_key: 'file', profile: { id: 'p', revision: 1 }, cell: { sheet: 'q', row: 5, column: 2 } },
    binding: { binding_id: 'b', binding_revision: 1, draft_revision: 2, base_revision: 1 },
    localRevision: 7, versions: { knowledge_snapshot_id: 'v1' } };
  const key = businessPrefetchKey(options);
  assert.notEqual(key, businessPrefetchKey({ ...options, localRevision: 8 }));
  assert.notEqual(key, businessPrefetchKey({ ...options, versions: { knowledge_snapshot_id: 'v2' } }));
  assert.notEqual(key, businessPrefetchKey({ ...options, context: { ...options.context, workbook_key: 'copy' } }));
  const cache = new BusinessPrefetch(); let calls = 0; let signal;
  cache.start(key, async (s) => { signal = s; calls++; return { items: [] }; });
  assert.deepEqual(await cache.take(key), { value: { items: [] } });
  assert.equal(cache.take(key), undefined); assert.equal(calls, 1);
  cache.start(key, async () => { throw new Error('网络中断'); });
  assert.match((await cache.take(key)).error.message, /网络/);
  cache.start(key, async (s) => { signal = s; return { items: [] }; });
  assert.equal(cache.take('new-version'), undefined); assert.equal(signal.aborted, true);
});

test('1000-row workbook performs no extra whole-sheet read for 20 ordinary edits', () => {
  let fullReads = 0, singleReads = 0;
  const data = Array.from({ length: 1000 }, (_, i) => ({ row: i + 2, values: { model: `m-${i}` } }));
  const index = new WorkbookRowIndex({ readRows: () => { fullReads++; return data; },
    readRow: (_, row) => { singleReads++; return data[row - 2]; } }, { sheet_selector: 'quote' });
  index.read();
  for (let i = 0; i < 20; i++) {
    index.changed({ sheet: 'quote', row: i + 2, rowCount: 1, structural: false });
    assert.equal(index.read().length, 1000);
  }
  assert.equal(fullReads, 1); assert.equal(singleReads, 20);
});

test('duplicate products after structural edits require explicit identity confirmation', () => {
  const bindings = [3, 4].map((row) => ({ line_id: `line-${row}`, sheet: 'q', row,
    anchor_fingerprint: 'same\0name', kind: 'software' }));
  const metadata = { schema_version: 2, line_bindings: bindings };
  const ids = ambiguousStructuralIdentities(metadata, 'q');
  assert.deepEqual(ids, ['line-3', 'line-4']);
  const result = scanWorkbook([{ sheet: 'q', row: 3, values: { model: 'same', name: 'name', quantity: '1' }, formula_fields: [] }],
    { ...metadata, business: { unresolved_line_ids: ids } });
  assert.equal(result.lines.length, 0); assert.match(result.unresolved[0], /重复身份/);
});

test('full completion request searches a filled 1000-row area without sequential host reads', () => {
  const rows = Array.from({ length: 1000 }, (_, i) => ({ sheet: 'q', row: i + 2,
    values: { model: `m${i}`, name: `n${i}`, quantity: '1' }, formula_fields: [], merged_fields: [] }));
  const metadata = { schema_version: 2, profile_revision: 1,
    binding: { binding_id: 'b', binding_revision: 1, draft_revision: 1, base_revision: 0, managed_device_ids: [] },
    line_bindings: rows.map((row) => ({ line_id: String(row.row), sheet: 'q', row: row.row,
      variant_id: 'v', source_id: 's', kind: 'software', confirmed_values: row.values,
      anchor_fingerprint: `${row.values.model}\0${row.values.name}` })),
    business: { local_revision: 0, scopes: [{ sheet: 'q', start_row: 2, end_row: 1002, system_id: 's' }], operations: [], recent_edits: [] } };
  let reads = 0, scans = 0;
  const host = { readRow: (_, row) => { reads++; return rows[row - 2] ?? {
    sheet: 'q', row, values: {}, formula_fields: [], merged_fields: [] }; },
    readRows: () => { scans++; return rows; }, businessRevision: () => 0 };
  const profile = { sheet_selector: 'q' };
  const index = new WorkbookRowIndex(host, profile);
  for (let i = 0; i < 20; i++) {
    const request = completionRequest({ host, index, profile, metadata,
      cell: { sheet: 'q', row: i + 2, column: 1 }, query: `m${i}` });
    assert.ok(request.target_cells.some((c) => c.row === 1002));
  }
  assert.equal(scans, 1); assert.equal(reads, 40);
});

test('non-ready and Shift Tab restore focus and use the WPS keyboard path, not Offset', () => {
  const calls = [];
  const native = (shift) => returnNativeTab({ shift, hide: () => calls.push('hide'), app: {
    OnKey: (key) => calls.push(['restore', key]), ActiveWindow: { Activate: () => calls.push('focus') },
    SendKeys: (...args) => calls.push(['send', ...args]),
  } });
  const complete = () => assert.fail('no candidate must never complete');
  for (let i = 0; i < 100; i++) handleInlineTab({ ready: false, shift: false, complete, native });
  handleInlineTab({ ready: true, shift: true, complete, native });
  assert.deepEqual(calls.slice(0, 4), ['hide', ['restore', '{TAB}'], 'focus', ['send', '{TAB}', true]]);
  assert.deepEqual(calls.at(-1), ['send', '+{TAB}', true]);
  assert.equal(calls.filter((c) => Array.isArray(c) && c[0] === 'send').length, 101);
});
