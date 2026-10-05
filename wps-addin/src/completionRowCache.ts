import type { WorkbookRowIndex } from './workbookRowIndex';
import type { SheetRow, WorkbookMetadata } from './types';
import { WorkbookBindings } from './workbookBindings.ts';
import { parseCompletionRows, type CompletionRows } from './completionRows.ts';

// Per-workbook index lifetime; no cross-file snapshots or timed expiry.
export class CompletionRowCache {
  private token: unknown;
  private bindingValues = new Map<string, string>();
  private bindings = new WorkbookBindings([]);
  private scopeStamp = '';
  private revision = -1;
  private generation = -1;
  private states = new Map<number, CompletionRows>();
  private aggregate?: CompletionRows;
  private override?: { key: string; state: CompletionRows };
  parsedRows = 0;

  binding(row: SheetRow) { return this.bindings.resolve(row) ?? this.bindings.at(row); }
  resolvedBinding(row: SheetRow) { return this.bindings.resolve(row); }

  read(options: { index: WorkbookRowIndex; metadata: WorkbookMetadata; token: unknown }) {
    const { index, metadata, token } = options;
    const snapshot = index.snapshot();
    const scopeStamp = JSON.stringify([metadata.business?.scopes, metadata.business?.unresolved_line_ids,
      metadata.schema_version, metadata.profile_revision]);
    const structural = this.generation !== snapshot.generation;
    if (structural) { this.states.clear(); this.revision = -1; this.override = undefined; }
    const dirty = new Set(index.changedRowsSince(this.revision));
    if (token !== this.token || structural) this.updateBindings(metadata, dirty);
    const scopesChanged = this.scopeStamp !== scopeStamp;
    const rows = new Map(snapshot.rows.map((row) => [row.row, row]));
    for (const row of this.states.keys()) if (!rows.has(row)) { this.states.delete(row); this.aggregate = undefined; }
    for (const row of snapshot.rows) {
      if (!scopesChanged && !dirty.has(row.row) && this.states.has(row.row)) continue;
      this.states.set(row.row, this.parse(row, metadata)); this.aggregate = undefined;
    }
    this.token = token; this.scopeStamp = scopeStamp;
    this.revision = snapshot.revision; this.generation = snapshot.generation;
    return this.aggregate ??= this.combine([...this.states.values()]);
  }

  private updateBindings(metadata: WorkbookMetadata, dirty: Set<number>) {
    const previous = this.bindingValues;
    this.bindingValues = new Map(metadata.line_bindings.map((b) => [b.line_id, JSON.stringify(b)]));
    const changed = new Set([...previous.keys(), ...this.bindingValues.keys()].filter((id) =>
      previous.get(id) !== this.bindingValues.get(id)));
    for (const [row, state] of this.states) {
      if (state.unresolved.length || [...state.presentLineIds].some((id) => changed.has(id))) dirty.add(row);
    }
    this.bindings = new WorkbookBindings(metadata.line_bindings);
    this.override = undefined;
  }

  private parse(row: SheetRow, metadata: WorkbookMetadata) {
    this.parsedRows++;
    const binding = this.binding(row);
    return parseCompletionRows([row], { ...metadata, line_bindings: binding ? [binding] : [] });
  }

  withActive(options: { row: SheetRow; metadata: WorkbookMetadata; included: boolean }) {
    const { row, metadata, included } = options;
    const key = JSON.stringify([included, row]);
    if (this.override?.key !== key) this.override = { key,
      state: included ? this.parse(row, metadata) : { lines: [], unresolved: [], presentLineIds: new Set() } };
    return this.combine([...this.states].filter(([number]) => number !== row.row)
      .map(([, state]) => state).concat(this.override.state));
  }

  private combine(states: CompletionRows[]): CompletionRows {
    const result: CompletionRows = { lines: [], unresolved: [], presentLineIds: new Set() };
    for (const state of states) {
      for (const line of state.lines) {
        if (!result.presentLineIds.has(line.line_id)) result.lines.push(line);
        else result.unresolved.push({ sheet: line.sheet, row: line.row,
          reason_code: 'duplicate_identity', system_id: null });
      }
      result.unresolved.push(...state.unresolved);
      state.presentLineIds.forEach((id) => result.presentLineIds.add(id));
    }
    return result;
  }
}
