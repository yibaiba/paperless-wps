import type {
  ActiveCell, Candidate, DiagnosticEventInput, DiagnosticEventPayload, InlineEditorContext,
  SheetRow, TemplateField, TemplateProfile, SuggestionFeedbackPayload, WorkbookMetadata,
} from './types';
import { CredentialStore } from './credentialStore.ts';
import type { WorkbookEditJournal } from './businessTypes';
import { MetadataRecords, readMetadataRecords, writeMetadataRecords } from './metadataRecords.ts';
import { sheetChange, subscribeHostEvent, type SheetChange } from './hostEvents.ts';
import { DiagnosticRecorder } from './diagnostics.ts';
import { enqueueFeedback, parseFeedbackOutbox, removeFeedback } from './feedbackOutbox.ts';
import { InlineDialogManager } from './inlineDialog.ts';
import type { InlineLayoutOptions, InlineLayoutResult } from './inlineLayout.ts';
import { WpsTabCoordinator } from './tabCoordinator.ts';
import { returnNativeTab } from './nativeTab.ts';
import { ambiguousStructuralIdentities, assertWritableTargets } from './workbook.ts';

declare global {
  interface Window {
    Application?: any;
    wps?: { EtApplication?: () => any };
    PresalesInlineRefresh?: () => void;
    PresalesInlineTab?: (sessionId: string) => void;
  }
}

const META_SHEET = '__PRESALES_META';
const META_CELL = 'A1';
const BACKGROUND_ERROR_KEY = 'presales_background_error';
const FEEDBACK_OUTBOX_KEY = 'presales_feedback_outbox';
const CONTEXT_LOOKBACK_ROWS = 100;

export interface HostAdapter {
  ready(): boolean;
  workbookKey(): string;
  token(): string | null;
  saveToken(value: string): void;
  account(): string | null;
  saveAccount(value: string): void;
  requestedAction(): string | null;
  clearRequestedAction(): void;
  activeCell(): ActiveCell;
  sheetNames(): string[];
  readHeader(sheet: string, row: number): string[];
  readRow(profile: TemplateProfile, row: number): SheetRow;
  readCell(cell: Pick<ActiveCell, 'sheet' | 'row' | 'column'>): ActiveCell;
  selectCell(cell: Pick<ActiveCell, 'sheet' | 'row' | 'column'>): void;
  journals(): WorkbookEditJournal[];
  writeJournal(journal: WorkbookEditJournal): void;
  readInheritedField(
    profile: TemplateProfile,
    options: { row: number; field: TemplateField },
  ): string;
  readRows(profile: TemplateProfile): SheetRow[];
  writeCandidate(profile: TemplateProfile, row: number, candidate: Candidate): void;
  readMetadata(): WorkbookMetadata;
  writeMetadata(value: WorkbookMetadata): void;
  metadataNonce(): number;
  inlineContext(): InlineEditorContext | null;
  showInlineEditor(profile: TemplateProfile, cell: ActiveCell): void;
  hideInlineEditor(): void;
  inlineCapabilityIssues(): string[];
  interceptTab(sessionId: string, revision: string): boolean;
  claimTab(sessionId: string): string | null;
  restoreNativeTab(sessionId?: string): boolean;
  recordDiagnostic(value: DiagnosticEventInput): DiagnosticEventPayload;
  pendingDiagnostics(): DiagnosticEventPayload[];
  removeDiagnostics(eventIds: string[]): void;
  layoutInlineEditor(
    options: Omit<InlineLayoutOptions, 'anchorWidth' | 'anchorHeight'>,
  ): InlineLayoutResult;
  backgroundError(): string | null;
  reportBackgroundError(message: string): void;
  clearBackgroundError(): void;
  pendingSuggestionFeedback(): SuggestionFeedbackPayload[];
  enqueueSuggestionFeedback(value: SuggestionFeedbackPayload): void;
  removeSuggestionFeedback(operationId: string): void;
  writeCellValue(cell: ActiveCell, value: string): void;
  moveSelection(rowOffset: number, columnOffset: number): void;
  returnNativeTab(shift: boolean): void;
  onSheetChange(callback: (event: SheetChange) => void): () => void;
  businessRevision(): number;
  onSelectionChange(callback: () => void): () => void;
  onSheetActivate(callback: () => void): () => void;
  onWorkbookBeforeClose(callback: () => void): () => void;
  onWorkbookActivate(callback: () => void): () => void;
}

function text(value: unknown) { return value == null ? '' : String(value); }

export class WpsHostAdapter implements HostAdapter {
  private readonly app: any;
  private readonly stateStorage?: Storage;
  private readonly credentials: CredentialStore;
  private readonly diagnostics: DiagnosticRecorder;
  private readonly inlineDialog: InlineDialogManager;
  private readonly tabCoordinator: WpsTabCoordinator;
  private recordStores = new Map<string, MetadataRecords>();

  constructor() {
    this.app = window.Application ?? window.wps?.EtApplication?.();
    const persistent = persistentStorage();
    this.stateStorage = persistent;
    this.credentials = new CredentialStore({
      shared: this.app?.PluginStorage,
      persistent,
    });
    if (!this.credentials.capabilityIssues().length) this.credentials.restore();
    this.inlineDialog = new InlineDialogManager({
      app: this.app,
      href: window.location?.href ?? 'http://127.0.0.1/',
      screen: window.screen,
      get: (key) => this.storeGet(key),
      set: (key, value) => this.storeSet(key, value),
    });
    this.tabCoordinator = new WpsTabCoordinator({
      app: this.app,
      get: (key) => this.storeGet(key),
      set: (key, value) => this.storeSet(key, value),
    });
    this.diagnostics = new DiagnosticRecorder({
      get: (key) => persistent?.getItem(key) ?? null,
      set: (key, value) => {
        if (!persistent) throw new Error('当前 WPS 缺少诊断本地存储能力');
        persistent.setItem(key, value);
      },
      installationId: () => this.credentials.installationId(),
      hostOs: () => String(window.navigator?.platform ?? 'unknown'),
      hostVersion: () => text(this.app?.Build ?? this.app?.Version) || 'unknown',
    });
  }

  ready() { return Boolean(this.app?.ActiveWorkbook); }

  workbookKey() {
    const workbook = this.requireWorkbook();
    return text(workbook.FullName ?? workbook.Name);
  }

  token() { return this.credentials.token(); }

  saveToken(value: string) { this.credentials.saveToken(value); }

  account() { return this.credentials.account(); }

  saveAccount(value: string) { this.credentials.saveAccount(value); }

  requestedAction() { return this.stateGet('presales_requested_action'); }

  clearRequestedAction() { this.stateSet('presales_requested_action', ''); }

  activeCell(): ActiveCell {
    this.requireWorkbook();
    const range = this.app.Selection;
    const sheet = this.app.ActiveSheet;
    if (!range || !sheet) throw new Error('请先选择工作表单元格');
    return {
      sheet: text(sheet.Name),
      row: Number(range.Row),
      column: Number(range.Column),
      value: text(range.Value2 ?? range.Text),
      formula: text(range.Formula),
      merged: Boolean(range.MergeCells),
    };
  }

  sheetNames() {
    const workbook = this.requireWorkbook();
    const names: string[] = [];
    for (let index = 1; index <= Number(workbook.Worksheets.Count); index += 1) {
      const name = text(workbook.Worksheets.Item(index).Name);
      if (name !== META_SHEET) names.push(name);
    }
    return names;
  }

  readHeader(sheetName: string, row: number) {
    const sheet = this.sheet(sheetName);
    const count = Math.min(Number(sheet.UsedRange?.Columns?.Count ?? 0), 200);
    const values = Array.from({ length: count }, (_, index) => this.cellText(sheet, row, index + 1));
    while (values.length && !values.at(-1)) values.pop();
    return values;
  }

  readRows(profile: TemplateProfile) {
    const sheet = this.sheet(profile.sheet_selector);
    const last = Number(sheet.UsedRange?.Rows?.Count ?? 0) + Number(sheet.UsedRange?.Row ?? 1) - 1;
    const rows: SheetRow[] = [];
    for (let row = profile.header_row + 1; row <= last; row += 1) {
      const current = this.mappedRow(sheet, profile, row);
      if (current.values.model?.trim() || current.values.name?.trim()) rows.push(current);
    }
    return rows;
  }

  readRow(profile: TemplateProfile, row: number) {
    return this.mappedRow(this.sheet(profile.sheet_selector), profile, row);
  }

  readCell(cell: Pick<ActiveCell, 'sheet' | 'row' | 'column'>): ActiveCell {
    const target = this.sheet(cell.sheet).Cells.Item(cell.row, cell.column);
    return { ...cell, value: text(target.Value2), formula: text(target.Formula),
      merged: Boolean(target.MergeCells) };
  }

  selectCell(cell: Pick<ActiveCell, 'sheet' | 'row' | 'column'>) {
    const sheet = this.sheet(cell.sheet);
    sheet.Activate();
    sheet.Cells.Item(cell.row, cell.column).Select();
  }

  readInheritedField(
    profile: TemplateProfile,
    options: { row: number; field: TemplateField },
  ) {
    const column = profile.field_columns[options.field];
    if (!column) return '';
    const sheet = this.sheet(profile.sheet_selector);
    const firstRow = Math.max(profile.header_row + 1, options.row - CONTEXT_LOOKBACK_ROWS);
    for (let row = options.row - 1; row >= firstRow; row -= 1) {
      const value = this.cellText(sheet, row, column);
      if (value) return value;
    }
    return '';
  }

  writeCandidate(profile: TemplateProfile, row: number, candidate: Candidate) {
    const sheet = this.sheet(profile.sheet_selector);
    const values: Partial<Record<TemplateField, string>> = {
      model: candidate.model,
      name: candidate.name,
      description: candidate.description,
      unit: candidate.unit,
      brand: candidate.brand,
    };
    const targets = profile.managed_fields.flatMap((field) => {
      const column = profile.field_columns[field];
      return column && values[field] !== undefined ? [{ field, column, value: values[field]! }] : [];
    });
    assertWritableTargets(targets.map((target) => {
      const cell = sheet.Cells.Item(row, target.column);
      return {
        address: this.address(row, target.column),
        formula: text(cell.Formula),
        merged: Boolean(cell.MergeCells),
      };
    }));
    for (const target of targets) sheet.Cells.Item(row, target.column).Value2 = target.value;
  }

  readMetadata(): WorkbookMetadata {
    const fallback: WorkbookMetadata = {
      schema_version: 1,
      workbook_instance_id: crypto.randomUUID(),
      line_bindings: [],
    };
    const sheet = this.optionalSheet(META_SHEET);
    if (!sheet) return fallback;
    const raw = text(sheet.Range(META_CELL).Value2);
    if (!raw) return fallback;
    try {
      const parsed = JSON.parse(raw) as WorkbookMetadata;
      if (parsed.schema_version === 2) return readMetadataRecords(this.records(sheet));
      if (parsed.schema_version !== 1) throw new Error('unsupported schema');
      return parsed;
    } catch {
      throw new Error('工作簿插件元数据损坏，请重新绑定项目');
    }
  }

  writeMetadata(value: WorkbookMetadata) {
    const workbook = this.requireWorkbook();
    const active = this.app.ActiveSheet;
    let sheet = this.optionalSheet(META_SHEET);
    if (!sheet) {
      sheet = workbook.Worksheets.Add();
      sheet.Name = META_SHEET;
    }
    if (value.schema_version === 2) writeMetadataRecords(this.records(sheet), value);
    else sheet.Range(META_CELL).Value2 = JSON.stringify(value);
    sheet.Visible = 2;
    if (active && active.Name !== META_SHEET) active.Activate();
    this.stateSet('presales_metadata_nonce', this.metadataNonce() + 1);
  }

  journals(): WorkbookEditJournal[] {
    const sheet = this.optionalSheet(META_SHEET);
    if (!sheet) return [];
    return Object.values(this.records(sheet).records('journal/')) as WorkbookEditJournal[];
  }

  writeJournal(journal: WorkbookEditJournal) {
    const metadata = this.readMetadata();
    if (metadata.schema_version !== 2) throw new Error('编辑日志需要先确认 v2 业务设置');
    this.records(this.sheet(META_SHEET)).write({ [`journal/${journal.operation_id}`]: journal });
  }

  private records(sheet: any) {
    const key = text(this.requireWorkbook().FullName ?? this.requireWorkbook().Name);
    let store = this.recordStores.get(key);
    if (!store) {
      store = new MetadataRecords({
        read: (row) => text(sheet.Cells.Item(row, 1).Value2),
        write: (row, value) => { sheet.Cells.Item(row, 1).Value2 = value; },
      });
      this.recordStores.set(key, store);
    }
    return store;
  }

  metadataNonce() { return Number(this.stateGet('presales_metadata_nonce') || 0); }

  inlineContext(): InlineEditorContext | null { return this.inlineDialog.context(); }

  showInlineEditor(profile: TemplateProfile, cell: ActiveCell) {
    if (cell.formula.startsWith('=') || cell.merged) return this.hideInlineEditor();
    const issues = this.inlineCapabilityIssues();
    if (issues.length) throw new Error(`当前 WPS 缺少内联补全能力：${issues.join('、')}`);
    const workbook = this.requireWorkbook();
    this.inlineDialog.show({ profile, cell, workbook_key: text(workbook.FullName ?? workbook.Name),
      binding_id: this.readMetadata().binding?.binding_id });
  }

  hideInlineEditor() {
    this.tabCoordinator.restore();
    this.inlineDialog.hide();
  }

  returnNativeTab(shift: boolean) {
    returnNativeTab({ app: this.app, hide: () => this.hideInlineEditor(), shift });
  }

  inlineCapabilityIssues() {
    const issues = [
      ...this.tabCoordinator.capabilityIssues(),
      ...this.credentials.capabilityIssues(),
    ];
    if (typeof this.app?.CreateWebDialog !== 'function') issues.push('CreateWebDialog');
    if (typeof this.app?.GetWebDialog !== 'function') issues.push('GetWebDialog');
    if (typeof this.app?.SendKeys !== 'function') issues.push('Application.SendKeys');
    if (typeof this.app?.ActiveWindow?.Activate !== 'function') issues.push('Window.Activate');
    if (typeof this.app?.ApiEvent?.AddApiEventListener !== 'function'
      || typeof this.app?.ApiEvent?.RemoveApiEventListener !== 'function') {
      issues.push('ApiEvent');
    }
    return [...new Set(issues)];
  }

  interceptTab(sessionId: string, revision: string) {
    return this.tabCoordinator.activate(sessionId, revision);
  }

  claimTab(sessionId: string) { return this.tabCoordinator.claim(sessionId); }

  restoreNativeTab(sessionId?: string) { return this.tabCoordinator.restore(sessionId); }

  recordDiagnostic(value: DiagnosticEventInput) { return this.diagnostics.record(value); }

  pendingDiagnostics() { return this.diagnostics.pending(); }

  removeDiagnostics(eventIds: string[]) { this.diagnostics.remove(eventIds); }

  layoutInlineEditor(options: Omit<InlineLayoutOptions, 'anchorWidth' | 'anchorHeight'>) {
    return this.inlineDialog.layout(options);
  }

  backgroundError() { return this.stateGet(BACKGROUND_ERROR_KEY); }

  reportBackgroundError(message: string) { this.stateSet(BACKGROUND_ERROR_KEY, message); }

  clearBackgroundError() { this.stateSet(BACKGROUND_ERROR_KEY, ''); }

  pendingSuggestionFeedback() {
    return parseFeedbackOutbox(this.stateGet(FEEDBACK_OUTBOX_KEY));
  }

  enqueueSuggestionFeedback(value: SuggestionFeedbackPayload) {
    this.stateSet(FEEDBACK_OUTBOX_KEY, enqueueFeedback(this.stateGet(FEEDBACK_OUTBOX_KEY), value));
  }

  removeSuggestionFeedback(operationId: string) {
    this.stateSet(
      FEEDBACK_OUTBOX_KEY,
      removeFeedback(this.stateGet(FEEDBACK_OUTBOX_KEY), operationId),
    );
  }

  writeCellValue(cell: ActiveCell, value: string) {
    const target = this.sheet(cell.sheet).Cells.Item(cell.row, cell.column);
    if (text(target.Formula).startsWith('=')) throw new Error('公式单元格不能用于产品联想');
    if (target.MergeCells) throw new Error('合并单元格不能用于产品联想');
    target.Value2 = value;
  }

  moveSelection(rowOffset: number, columnOffset: number) {
    const selection = this.app.Selection;
    selection.Offset(rowOffset, columnOffset).Select();
  }

  businessRevision() {
    const metadata = this.readMetadata();
    return (metadata.business?.local_revision ?? 0) + Number(this.stateGet(this.editKey()) || 0);
  }

  private editKey() {
    return `presales_edit_epoch:${text(this.requireWorkbook().FullName ?? this.requireWorkbook().Name)}`;
  }

  onSheetChange(callback: (event: SheetChange) => void) {
    return this.event('SheetChange', (sheet: unknown, target: unknown) => {
      const change = sheetChange(sheet, target);
      if (change.sheet === META_SHEET) return;
      this.stateSet(this.editKey(), Number(this.stateGet(this.editKey()) || 0) + 1);
      if (change.structural) {
        const metadata = this.readMetadata();
        if (metadata.business) {
          const before = metadata.business.unresolved_line_ids ?? [];
          const ids = [...new Set([...before, ...ambiguousStructuralIdentities(metadata, change.sheet)])];
          if (ids.length !== before.length) this.writeMetadata({ ...metadata,
            business: { ...metadata.business, unresolved_line_ids: ids } });
        }
      }
      callback(change);
    });
  }

  onSelectionChange(callback: () => void) { return this.event('SheetSelectionChange', callback); }

  onSheetActivate(callback: () => void) { return this.event('SheetActivate', callback); }

  onWorkbookBeforeClose(callback: () => void) {
    return this.event('WorkbookBeforeClose', () => { this.recordStores.clear(); callback(); });
  }

  onWorkbookActivate(callback: () => void) { return this.event('WorkbookActivate', callback); }

  private event(name: string, callback: (...args: any[]) => void) {
    return subscribeHostEvent(this.app.ApiEvent, name, callback);
  }

  private requireWorkbook() {
    if (!this.app?.ActiveWorkbook) throw new Error('请先在 WPS 表格中打开工作簿');
    return this.app.ActiveWorkbook;
  }

  private sheet(name: string) {
    const sheet = this.optionalSheet(name);
    if (!sheet) throw new Error(`工作表“${name}”不存在，请重新映射模板`);
    return sheet;
  }

  private optionalSheet(name: string) {
    const workbook = this.requireWorkbook();
    try { return workbook.Worksheets.Item(name); } catch { return null; }
  }

  private cellText(sheet: any, row: number, column: number) {
    const cell = sheet.Cells.Item(row, column);
    return text(cell.Text ?? cell.Value2).trim();
  }

  private mappedRow(sheet: any, profile: TemplateProfile, row: number) {
    const values: SheetRow['values'] = {};
    const formulaFields: TemplateField[] = [];
    const mergedFields: TemplateField[] = [];
    const fields = Object.entries(profile.field_columns) as Array<[TemplateField, number]>;
    for (const [field, column] of fields) {
      const cell = sheet.Cells.Item(row, column);
      values[field] = text(cell.Value2 ?? cell.Text);
      if (text(cell.Formula).startsWith('=')) formulaFields.push(field);
      if (cell.MergeCells) mergedFields.push(field);
    }
    return {
      sheet: profile.sheet_selector, row, values,
      formula_fields: formulaFields, merged_fields: mergedFields,
    };
  }

  private storeGet(key: string) {
    try { return text(this.app?.PluginStorage?.getItem(key)) || null; }
    catch { return localStorage.getItem(key); }
  }

  private storeSet(key: string, value: string | number) {
    try { this.app?.PluginStorage?.setItem(key, value); }
    catch { localStorage.setItem(key, String(value)); }
  }

  private stateGet(key: string) {
    if (!this.stateStorage) throw new Error('当前 WPS 缺少加载项本地状态存储能力');
    return this.stateStorage.getItem(key);
  }

  private stateSet(key: string, value: string | number) {
    if (!this.stateStorage) throw new Error('当前 WPS 缺少加载项本地状态存储能力');
    this.stateStorage.setItem(key, String(value));
  }

  private address(row: number, column: number) {
    let name = '';
    for (let value = column; value > 0; value = Math.floor((value - 1) / 26)) {
      name = String.fromCharCode(65 + ((value - 1) % 26)) + name;
    }
    return `${name}${row}`;
  }
}

function persistentStorage() {
  try { return window.localStorage; }
  catch { return undefined; }
}
