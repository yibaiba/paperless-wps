import type { SheetChange } from './hostEvents';
import type { HostAdapter } from './host';
import type { SheetRow, TemplateProfile } from './types';

export class WorkbookRowIndex {
  private rows: Map<number, SheetRow> | undefined;
  private staleRows = new Set<number>();
  private observedRows = new Map<number, SheetRow>();
  private edits = new Map<number, { before: SheetRow; after: SheetRow; order: number; historyKey: string }>();
  private editOrder = 0;
  private readonly host: Pick<HostAdapter, 'readRows' | 'readRow'>;
  private readonly profile: TemplateProfile;
  constructor(host: Pick<HostAdapter, 'readRows' | 'readRow'>, profile: TemplateProfile) {
    this.host = host; this.profile = profile;
  }
  changed(event: SheetChange, options: { recordEdit?: boolean; historyKey?: string } = {}) {
    if (event.sheet !== this.profile.sheet_selector) return;
    if (event.structural) { this.rows = undefined; this.observedRows.clear(); this.staleRows.clear(); this.edits.clear(); return; }
    if (!this.rows) return;
    for (let row = event.row; row < event.row + event.rowCount; row += 1) {
      const before = this.rows.get(row);
      const after = this.refresh(row);
      if (options.recordEdit !== false && before && JSON.stringify(before.values) !== JSON.stringify(after.values)) {
        this.edits.set(row, { before, after, order: this.editOrder++, historyKey: options.historyKey ?? '' });
      }
    }
  }
  recentChanges() {
    return [...this.edits.values()].sort((a, b) => a.order - b.order);
  }
  refresh(row: number) {
    this.staleRows.add(row);
    const value = this.host.readRow(this.profile, row);
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
