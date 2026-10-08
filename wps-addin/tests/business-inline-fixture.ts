// Test-only memory adapter and controlled responses. Never imported by production entrypoints.
import { WpsTabCoordinator } from '../src/tabCoordinator';
import { inlineDialogSize } from '../src/inlineLayout';
import type { CompletionPreviewResult, NextEditSuggestion } from '../src/businessTypes';

export type Scenario = 'choice' | 'preview' | 'off-row' | 'off-row-preview' | 'refresh-error'
  | 'slow-choice' | 'same-name' | 'continuation' | 'undo-refresh-error' | 'slow-prefetch' | 'slow-query';

export function businessInlineFixture(scenario: Scenario, notify: () => void) {
  const sheet = '隔离测试表';
  const offRow = scenario === 'off-row' || scenario === 'off-row-preview';
  const continuation = ['continuation', 'undo-refresh-error', 'slow-prefetch'].includes(scenario);
  const initialInput = offRow || continuation ? '' : '服';
  const profile = { id: 'fixture-profile', revision: 1, schema_version: 2, sheet_selector: sheet,
    header_row: 1, field_columns: { model: 1, name: 2, quantity: 3 }, managed_fields: ['model', 'name'] };
  let metadata: any = { schema_version: 2, workbook_instance_id: 'fixture', line_bindings: [],
    binding: { binding_id: 'fixture-binding', binding_revision: 1, draft_revision: 1, base_revision: 1, managed_device_ids: [] },
    business: { local_revision: 0, operations: [], recent_edits: [],
      scopes: [{ sheet, start_row: 3, end_row: 8, system_id: 'system', room_id: 'room' }] } };
  let context: any = { workbook_key: 'fixture.xlsx', binding_id: 'fixture-binding', profile,
    cell: { sheet, row: 3, column: 2, value: initialInput, formula: '', merged: false },
    nonce: 1, session_id: 'session-1', anchor: { width: 360, height: 32 } };
  const values = new Map<string, string>([['3:2', initialInput], ['3:3', '1']]);
  if (offRow || continuation) values.set('4:3', '1');
  const journals = new Map();
  const storage = new Map();
  const stats = { requests: 0, choices: 0, writes: 0, located: 0, nativeTabs: 0, height: 32,
    selectedVariant: '', pending: false, cancelled: 0, row: 3, lastRequest: '', requestedProducts: [] as string[] };
  let failRead = scenario === 'refresh-error';
  let failUndoRead = scenario === 'undo-refresh-error';
  let release: (() => void) | undefined;
  const coordinator = new WpsTabCoordinator({ app: { OnKey() {} },
    get: (key) => storage.get(key), set: (key, value) => storage.set(key, value) });
  const readRow = (row: number) => {
    if (failRead && metadata.business.local_revision > 0) throw new Error('测试故障：写入后的读行失败');
    if (failUndoRead && metadata.business.recent_edits.at(-1)?.kind === 'undo') throw new Error('测试故障：撤销后的读行失败');
    return { sheet, row, values: { model: values.get(`${row}:1`) ?? '', name: values.get(`${row}:2`) ?? '',
      quantity: values.get(`${row}:3`) ?? '' }, formula_fields: [], merged_fields: [] };
  };
  const host = {
    inlineContext: () => context, workbookKey: () => 'fixture.xlsx',
    readMetadata: () => structuredClone(metadata), writeMetadata: (next: any) => { metadata = next; notify(); },
    businessRevision: () => metadata.business.local_revision,
    onSheetChange: () => () => {},
    readRow: (_: unknown, row: number) => readRow(row),
    readRows: () => [3, 4].map(readRow).filter((row) => row.values.name || row.values.model),
    readCell: (cell: any) => ({ ...cell, value: values.get(`${cell.row}:${cell.column}`) ?? '', formula: '', merged: false }),
    writeCellValue: (cell: any, value: string) => { values.set(`${cell.row}:${cell.column}`, value); stats.writes++; notify(); },
    journals: () => [...journals.values()], writeJournal: (journal: any) => { journals.set(journal.operation_id, journal); notify(); },
    interceptTab: (session: string, revision: string) => coordinator.activate(session, revision),
    restoreNativeTab: (session?: string) => coordinator.restore(session),
    claimTab: (session: string) => coordinator.claim(session),
    returnNativeTab: () => { stats.nativeTabs++; host.hideInlineEditor(); },
    hideInlineEditor: () => { context = null; coordinator.restore(); window.PresalesInlineRefresh?.(); notify(); },
    selectCell: (cell: any) => { stats.located++; stats.row = cell.row; notify(); },
    showInlineEditor: (_: unknown, cell: any) => {
      context = { ...context, cell, nonce: context.nonce + 1, session_id: crypto.randomUUID() };
    },
    layoutInlineEditor: (options: any) => {
      const height = inlineDialogSize({ ...options, anchorWidth: 360, anchorHeight: 32 }).height;
      if (height !== stats.height) { stats.height = height; notify(); }
      return { placement: 'below', anchor: { width: 360, height: 32 } };
    },
    reportBackgroundError: (message: string) => { throw new Error(message); },
  };
  function candidate(variant: string, applicable: boolean): NextEditSuggestion {
    const row = offRow || (continuation && variant === 'B') ? 4 : context.cell.row;
    const before = readRow(row).values;
    const after = { ...before, model: scenario === 'same-name' ? 'SERVER' : `SERVER-${variant}`,
      name: scenario === 'same-name' ? '服务器' : `服务器 ${variant}`, quantity: '1' };
    const patches = (['model', 'name'] as const).map((field) => ({ sheet, row,
      column: profile.field_columns[field], field, before: before[field], after: after[field] }));
    return { id: `suggestion-${variant}`, kind: 'product', label: `隔离产品 ${variant}`, patches,
      line_bindings: [{ line_id: `line-${variant}`, device_id: `device-${variant}`, variant_id: variant,
        source_id: `source-${variant}`, kind: 'hardware', sheet, row, confirmed_values: after,
        anchor_fingerprint: `${after.model}\0${after.name}`.toLowerCase(), section: '' }],
      business_operations: [], changes: [{ kind: 'devices', id: `device-${variant}`, before: null,
        after: { id: `device-${variant}`, variant_snapshot: { name: `配置 ${variant}`, description: `测试规格 ${variant}` },
          source_snapshot: { sheet: '测试目录', row: 10 + variant.charCodeAt(0) - 'A'.charCodeAt(0), import_id: `batch-${variant}` } } }],
      evidence: ['隔离测试，不构成真实配套依据'],
      issues: applicable ? [] : ['请明确选择配置'], applicable,
      acceptance: scenario === 'preview' || scenario === 'off-row-preview' ? 'preview' : 'inline',
      context_fingerprint: 'fixture-context', local_revision: metadata.business.local_revision };
  }
  const api = { completionPreview: async (body: any, _signal?: AbortSignal): Promise<CompletionPreviewResult> => {
    stats.requests++; stats.lastRequest = body.query;
    stats.requestedProducts = body.lines.map((line: { variant_id: string }) => line.variant_id);
    const selected = body.selected_variant_id;
    if (selected) { stats.choices++; stats.selectedVariant = selected; }
    notify();
    if (selected && scenario === 'slow-choice') {
      stats.pending = true; notify();
      await new Promise<void>((resolve) => { release = resolve; });
      stats.pending = false; notify();
    }
    if (scenario === 'slow-prefetch' && metadata.line_bindings.length && !body.query) {
      stats.pending = true; notify();
      try {
        await new Promise<void>((resolve, reject) => {
          const abort = () => { stats.cancelled++; notify(); reject(new DOMException('测试请求已取消', 'AbortError')); };
          if (_signal?.aborted) { abort(); return; }
          _signal?.addEventListener('abort', abort, { once: true });
          release = () => { _signal?.removeEventListener('abort', abort); resolve(); };
        });
      } finally { stats.pending = false; notify(); }
    }
    const undone = continuation && metadata.business.recent_edits.at(-1)?.kind === 'undo';
    const done = continuation ? metadata.line_bindings.length === 2 || undone : metadata.business.local_revision > 0;
    const items = done ? [] : continuation ? [candidate(metadata.line_bindings.length ? 'B' : 'A', true)]
      : selected ? [candidate(selected, true)]
      : scenario === 'refresh-error' ? [candidate('A', true)]
      : (scenario === 'same-name' ? ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'] : ['A', 'B']).map((id) => candidate(id, false));
    const response: CompletionPreviewResult = { items, issues: undone ? ['测试轨迹已撤销，等待新的明确输入'] : [], context_fingerprint: 'fixture-context', versions: {},
      local_revision: metadata.business.local_revision, line_bindings: [], configuration: {} as never,
      context_summary: { mode: 'business', project_id: 'test-only-project', scope: metadata.business.scopes[0],
        detail: 'inline', row_count: body.lines.length, rows_omitted: 0,
        system: { id: 'system', name: '隔离测试系统', kind: 'test-only' }, room: { id: 'room', name: '隔离测试房间' },
        versions: { catalog_snapshot_id: 'test-only-snapshot' }, local_revision: metadata.business.local_revision,
        catalog_scope: { import_id: 'test-only-import', sheet: '隔离目录' },
        rows: body.lines.map((line: any) => ({ ...line, id: line.device_id ?? line.line_id,
          participation: 'dependency', supply_allocations: [], uses: [] })),
        local_change_count: metadata.line_bindings.length, local_changes_omitted: 0,
        local_changes: metadata.line_bindings.map((line: any) => ({ kind: 'devices', id: line.device_id })),
        knowledge: [], issues: [] },
      primary_suggestion_id: items.length === 1 ? items[0].id : null,
      decision: { status: done ? 'satisfied' : items.length === 1 ? 'ready' : 'choice_required',
        reason_code: done ? 'requirements_satisfied' : items.length === 1 ? 'unique_candidate' : 'variant_ambiguous' } };
    if (scenario === 'slow-query' && stats.requests === 1) {
      stats.pending = true; notify();
      await new Promise<void>((resolve) => { release = resolve; });
      stats.pending = false; notify();
    }
    return response;
  } };
  return { host, api, stats, journals, values,
    switchBeforeReply: () => {
      // Reproduce a host session change before React receives its refresh event.
      const cell = host.readCell({ sheet, row: 4, column: 2 });
      host.selectCell(cell); host.showInlineEditor(profile, cell); release?.();
    },
    refreshContext: () => window.PresalesInlineRefresh?.(),
    release: () => release?.(), repairRead: () => { failRead = false; failUndoRead = false; notify(); } };
}
