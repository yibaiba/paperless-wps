import type { LineBinding, SheetRow } from './types';
import { rowAnchor } from './workbook.ts';

export class WorkbookBindings {
  private readonly positions = new Map<string, LineBinding>();
  private readonly anchors = new Map<string, LineBinding[]>();
  constructor(bindings: readonly LineBinding[]) {
    for (const binding of bindings) {
      this.positions.set(this.position(binding), binding);
      if (!binding.anchor_fingerprint) continue;
      const key = `${binding.sheet}\0${binding.anchor_fingerprint}`;
      this.anchors.set(key, [...this.anchors.get(key) ?? [], binding]);
    }
  }
  private position(row: Pick<SheetRow, 'sheet' | 'row'>) { return `${row.sheet}\0${row.row}`; }
  at(row: Pick<SheetRow, 'sheet' | 'row'>) { return this.positions.get(this.position(row)); }
  resolve(row: SheetRow) {
    const exact = this.at(row);
    const anchor = rowAnchor(row);
    if (exact && (!exact.anchor_fingerprint || exact.anchor_fingerprint === anchor)) return exact;
    const matches = this.anchors.get(`${row.sheet}\0${anchor}`) ?? [];
    return matches.length === 1 ? matches[0] : undefined;
  }
}
