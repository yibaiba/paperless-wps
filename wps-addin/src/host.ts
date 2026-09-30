import type {
  ActiveCell, Candidate, InlineEditorContext, SheetRow, TemplateField, TemplateProfile,
  SuggestionFeedbackPayload, WorkbookMetadata,
} from './types';
import { enqueueFeedback, parseFeedbackOutbox, removeFeedback } from './feedbackOutbox.ts';
import { InlineDialogManager } from './inlineDialog.ts';
import type { InlineLayoutOptions, InlineLayoutResult } from './inlineLayout.ts';
import { assertWritableTargets } from './workbook.ts';

declare global {
  interface Window {
    Application?: any;
    wps?: { EtApplication?: () => any };
    PresalesInlineRefresh?: () => void;
  }
}

const META_SHEET = '__PRESALES_META';
const META_CELL = 'A1';
const INLINE_ADVANCE_KEY = 'presales_inline_advance';
const BACKGROUND_ERROR_KEY = 'presales_background_error';
const FEEDBACK_OUTBOX_KEY = 'presales_feedback_outbox';
const CONTEXT_LOOKBACK_ROWS = 100;

export interface HostAdapter {
  ready(): boolean;
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
  layoutInlineEditor(
    options: Omit<InlineLayoutOptions, 'anchorWidth' | 'anchorHeight'>,
  ): InlineLayoutResult;
  requestInlineAdvance(): void;
  consumeInlineAdvance(): boolean;
  backgroundError(): string | null;
  reportBackgroundError(message: string): void;
  clearBackgroundError(): void;
  pendingSuggestionFeedback(): SuggestionFeedbackPayload[];
  enqueueSuggestionFeedback(value: SuggestionFeedbackPayload): void;
  removeSuggestionFeedback(operationId: string): void;
  writeCellValue(cell: ActiveCell, value: string): void;
  moveSelection(rowOffset: number, columnOffset: number): void;
  onSheetChange(callback: () => void): () => void;
  onSelectionChange(callback: () => void): () => void;
}

function text(value: unknown) { return value == null ? '' : String(value); }

export class WpsHostAdapter implements HostAdapter {
  private readonly app: any;
  private readonly inlineDialog: InlineDialogManager;

  constructor() {
    this.app = window.Application ?? window.wps?.EtApplication?.();
    this.inlineDialog = new InlineDialogManager({
      app: this.app,
      href: window.location?.href ?? 'http://127.0.0.1/',
      screen: window.screen,
      get: (key) => this.storeGet(key),
      set: (key, value) => this.storeSet(key, value),
    });
  }

  ready() { return Boolean(this.app?.ActiveWorkbook); }

  token() { return this.storeGet('presales_access_token'); }

  saveToken(value: string) { this.storeSet('presales_access_token', value); }

  account() { return this.storeGet('presales_account'); }

  saveAccount(value: string) { this.storeSet('presales_account', value); }

  requestedAction() { return this.storeGet('presales_requested_action'); }

  clearRequestedAction() { this.storeSet('presales_requested_action', ''); }

  activeCell(): ActiveCell {
    this.requireWorkbook();
    const range = this.app.Selection;
    const sheet = this.app.ActiveSheet;
    if (!range || !sheet) throw new Error('请先选择工作表单元格');
    return {
      sheet: text(sheet.Name),
      row: Number(range.Row),
      column: Number(range.Column),
      value: text(range.Text ?? range.Value2),
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
    sheet.Range(META_CELL).Value2 = JSON.stringify(value);
    sheet.Visible = 2;
    if (active && active.Name !== META_SHEET) active.Activate();
    this.storeSet('presales_metadata_nonce', this.metadataNonce() + 1);
  }

  metadataNonce() { return Number(this.storeGet('presales_metadata_nonce') || 0); }

  inlineContext(): InlineEditorContext | null { return this.inlineDialog.context(); }

  showInlineEditor(profile: TemplateProfile, cell: ActiveCell) {
    if (cell.formula || cell.merged) return this.hideInlineEditor();
    this.inlineDialog.show({ profile, cell });
  }

  hideInlineEditor() { this.inlineDialog.hide(); }

  layoutInlineEditor(options: Omit<InlineLayoutOptions, 'anchorWidth' | 'anchorHeight'>) {
    return this.inlineDialog.layout(options);
  }

  requestInlineAdvance() { this.storeSet(INLINE_ADVANCE_KEY, Date.now()); }

  consumeInlineAdvance() {
    if (!this.storeGet(INLINE_ADVANCE_KEY)) return false;
    this.storeSet(INLINE_ADVANCE_KEY, '');
    return true;
  }

  backgroundError() { return this.storeGet(BACKGROUND_ERROR_KEY); }

  reportBackgroundError(message: string) { this.storeSet(BACKGROUND_ERROR_KEY, message); }

  clearBackgroundError() { this.storeSet(BACKGROUND_ERROR_KEY, ''); }

  pendingSuggestionFeedback() {
    return parseFeedbackOutbox(this.storeGet(FEEDBACK_OUTBOX_KEY));
  }

  enqueueSuggestionFeedback(value: SuggestionFeedbackPayload) {
    this.storeSet(FEEDBACK_OUTBOX_KEY, enqueueFeedback(this.storeGet(FEEDBACK_OUTBOX_KEY), value));
  }

  removeSuggestionFeedback(operationId: string) {
    this.storeSet(
      FEEDBACK_OUTBOX_KEY,
      removeFeedback(this.storeGet(FEEDBACK_OUTBOX_KEY), operationId),
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

  onSheetChange(callback: () => void) { return this.event('SheetChange', callback); }

  onSelectionChange(callback: () => void) { return this.event('SheetSelectionChange', callback); }

  private event(name: string, callback: () => void) {
    const handler = () => callback();
    this.app.ApiEvent.AddApiEventListener(name, handler);
    return () => this.app.ApiEvent.RemoveApiEventListener(name, handler);
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
      values[field] = text(cell.Text ?? cell.Value2);
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

  private address(row: number, column: number) {
    let name = '';
    for (let value = column; value > 0; value = Math.floor((value - 1) / 26)) {
      name = String.fromCharCode(65 + ((value - 1) % 26)) + name;
    }
    return `${name}${row}`;
  }
}
