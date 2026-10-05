import assert from 'node:assert/strict';
import { test } from 'node:test';
import { contextWorkload } from './context-workload.mjs';
import { scanWorkbook } from '../src/workbook.ts';
import { navigateResolution, requestedResolution, resolutionActions } from '../src/resolutionActions.ts';

test('unresolved rows are sent to the dependency engine, not removed or used as zero stock', () => {
  const work = contextWorkload(4);
  work.rows[1] = { ...work.rows[1], values: { ...work.rows[1].values, quantity: '待确认' } };
  const request = work.request();
  assert.equal(request.lines.length, 3);
  assert.equal(request.unresolved_rows.length, 1);
  assert.equal(request.unresolved_rows[0].row, 3);
  assert.equal(request.unresolved_rows[0].line_id, '3');
  assert.equal(request.unresolved_rows[0].confirmed_line.quantity, '1');
  assert.equal(request.removed_lines.length, 0);
  assert.ok(scanWorkbook(work.rows, work.metadata).unresolved.length);
});

test('manually changed identity is unresolved but retains the previous identity', () => {
  const work = contextWorkload(4);
  work.rows[1] = { ...work.rows[1], values: { ...work.rows[1].values, model: '新型号' } };
  const request = work.request();
  assert.equal(request.unresolved_rows[0].confirmed_line.model, 'm1');
  assert.deepEqual(request.removed_lines, []);
  work.rows.splice(1, 1);
  work.index.changed({ sheet: 'q', structural: true });
  const deleted = work.request();
  assert.deepEqual(deleted.removed_lines.map((line) => line.line_id), ['3']);
});

test('unsubmitted current input is only a query, not a confirmed new business line', () => {
  const work = contextWorkload(4);
  work.metadata.line_bindings = work.metadata.line_bindings.slice(1);
  const request = work.request('服务器');
  assert.equal(request.lines.length, 3);
  assert.equal(request.unresolved_rows.length, 0);
});

const action = { kind: 'confirm_identity', label: '确认这一行', sheet: 'q', row: 30, column: 1,
  expected_local_revision: 1, context_fingerprint: 'fp', binding_id: 'b', template_profile_revision: 2 };

test('resolution actions navigate and open existing panels without writing or confirming facts', () => {
  const calls = [];
  const host = { readMetadata: () => ({ binding: { binding_id: 'b' }, profile_revision: 2 }),
    businessRevision: () => 1, selectCell: (cell) => calls.push(['select', cell.row]),
    hideInlineEditor: () => calls.push(['hide']), openTaskPaneAction: (raw) => calls.push(['pane', requestedResolution(raw).kind]) };
  assert.deepEqual(resolutionActions({ resolution_actions: [action] }), [action]);
  navigateResolution({ host, action, fingerprint: 'fp' });
  assert.deepEqual(calls, [['select', 30], ['hide'], ['pane', 'confirm_identity']]);
  host.businessRevision = () => 2;
  assert.throws(() => navigateResolution({ host, action, fingerprint: 'fp' }), /上下文已变化/);
  assert.equal(calls.length, 3);
  assert.throws(() => requestedResolution(JSON.stringify({ ...action, row: -1 })), /协议/);
});
