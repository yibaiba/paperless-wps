import type { SheetChange } from './hostEvents';
import type { HostAdapter } from './host';
import type { SheetRow, TemplateProfile } from './types';

export class WorkbookRowIndex {
  private rows: Map<number, SheetRow> | undefined;
  private edits = new Map<number, { before: SheetRow; after: SheetRow; order: number; historyKey: string }>();
  private editOrder = 0;
  private readonly host: Pick<HostAdapter, 'readRows' | 'readRow'>;
  private readonly profile: TemplateProfile;
  constructor(host: Pick<HostAdapter, 'readRows' | 'readRow'>, profile: TemplateProfile) {
    this.host = host; this.profile = profile;
  }
  changed(event: SheetChange, options: { recordEdit?: boolean; historyKey?: string } = {}) {
    if (event.sheet !== this.profile.sheet_selector) return;
    if (event.structural) { this.rows = undefined; this.edits.clear(); return; }
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
    const value = this.host.readRow(this.profile, row);
    if (value.values.model?.trim() || value.values.name?.trim()) this.rows?.set(row, value);
    else this.rows?.delete(row);
    return value;
  }
  read() {
    if (!this.rows) this.rows = new Map(this.host.readRows(this.profile).map((row) => [row.row, row]));
    return [...this.rows.values()].sort((a, b) => a.row - b.row);
  }
}
