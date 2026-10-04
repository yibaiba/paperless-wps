import type { SheetChange } from './hostEvents';
import type { HostAdapter } from './host';
import type { SheetRow, TemplateProfile } from './types';

interface PendingChange { before?: SheetRow; historyKey: string; order: number }

export class WorkbookRowIndex {
  private rows: Map<number, SheetRow> | undefined;
  private staleRows = new Set<number>();
  private observedRows = new Map<number, SheetRow>();
  private pendingChanges = new Map<number, PendingChange>();
  private edits = new Map<number, { before: SheetRow; after: SheetRow; order: number; historyKey: string }>();
  private editOrder = 0;
  private readonly host: Pick<HostAdapter, 'readRows' | 'readRow'>;
  private readonly profile: TemplateProfile;
  constructor(host: Pick<HostAdapter, 'readRows' | 'readRow'>, profile: TemplateProfile) {
    this.host = host; this.profile = profile;
  }
  changed(event: SheetChange, options: { recordEdit?: boolean; historyKey?: string } = {}) {
    if (event.sheet !== this.profile.sheet_selector) return;
    if (event.structural) {
      this.rows = undefined; this.observedRows.clear(); this.staleRows.clear();
      this.pendingChanges.clear(); this.edits.clear(); return;
    }
    if (!this.rows) return;
    // Invalidate the entire host range before IO: a failed first read must not
    // leave later pasted rows cached as current or discard their edit evidence.
    for (let row = event.row; row < event.row + event.rowCount; row += 1) {
      this.staleRows.add(row);
      if (options.recordEdit === false) this.pendingChanges.delete(row);
      else if (!this.pendingChanges.has(row)) this.pendingChanges.set(row,
        { before: this.rows.get(row), order: this.editOrder++, historyKey: options.historyKey ?? '' });
    }
    for (let row = event.row; row < event.row + event.rowCount; row += 1) this.refresh(row);
  }
  private recordChange(after: SheetRow) {
    const pending = this.pendingChanges.get(after.row);
    if (!pending?.before || JSON.stringify(pending.before.values) === JSON.stringify(after.values)) return;
    const previous = this.edits.get(after.row);
    // Notes or input text may update row contents, but not the order or original
    // values of the last committed quantity change in the same business history.
    if (previous?.historyKey === pending.historyKey && pending.before.values.quantity === after.values.quantity) {
      this.edits.set(after.row, { ...previous, after });
      return;
    }
    this.edits.set(after.row, { ...pending, before: pending.before, after });
  }
  recentChanges() {
    return [...this.edits.values()].sort((a, b) => a.order - b.order);
  }
  refresh(row: number) {
    this.staleRows.add(row);
    const value = this.host.readRow(this.profile, row);
    this.recordChange(value);
    this.pendingChanges.delete(row);
    this.observedRows.set(row, value);
    if (value.values.model?.trim() || value.values.name?.trim()) this.rows?.set(row, value);
    else this.rows?.delete(row);
    this.staleRows.delete(row);
    return value;
  }
  peek(row: number) {
    if (this.staleRows.has(row)) return this.refresh(row);
    return this.observedRows.get(row) ?? this.refresh(row);
  }
  refreshRows(cells: ReadonlyArray<{ sheet: string; row: number }>) {
    const rows = new Set(cells.filter((cell) => cell.sheet === this.profile.sheet_selector).map((cell) => cell.row));
    // Mark the whole group before reading: a failed host read must not leave
    // later rows looking current when the user retries the query.
    rows.forEach((row) => this.staleRows.add(row));
    rows.forEach((row) => this.refresh(row));
  }
  read() {
    if (!this.rows) {
      this.rows = new Map(this.host.readRows(this.profile).map((row) => [row.row, row]));
      this.rows.forEach((row, number) => this.observedRows.set(number, row));
      this.staleRows.clear();
    }
    this.staleRows.forEach((row) => this.refresh(row));
    return [...this.rows.values()].sort((a, b) => a.row - b.row);
  }
}
