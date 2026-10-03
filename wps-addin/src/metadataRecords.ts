import type { WorkbookMetadata } from './types';

// Below the spreadsheet cell text limit (32,767 UTF-16 code units).
const RECORD_CHUNK_SIZE = 30_000;
interface Location { row: number; count: number }
interface Manifest { format: 'presales-records-v2'; next: number; records: Record<string, Location> }
export interface RecordCells { read(row: number): string; write(row: number, value: string): void }

export class MetadataRecords {
  private cache = new Map<string, { location: string; value: string }>();
  private readonly cells: RecordCells;
  constructor(cells: RecordCells) { this.cells = cells; }

  private manifest(): Manifest {
    const header = JSON.parse(this.cells.read(1) || '{}');
    if (header.format !== 'presales-records-v2') {
      return { format: 'presales-records-v2', next: 2, records: {} };
    }
    const raw = this.readLocation(header.manifest);
    const result = JSON.parse(raw) as Manifest;
    if (result.format !== 'presales-records-v2' || !Number.isSafeInteger(result.next)) {
      throw new Error('工作簿记录索引损坏');
    }
    return result;
  }

  private readLocation(location: Location) {
    if (!Number.isSafeInteger(location.row) || location.row < 2
      || !Number.isSafeInteger(location.count) || location.count < 1) {
      throw new Error('工作簿记录位置损坏');
    }
    return Array.from({ length: location.count }, (_, i) => this.cells.read(location.row + i)).join('');
  }

  records(prefix: string): Record<string, unknown> {
    const manifest = this.manifest();
    return Object.fromEntries(Object.entries(manifest.records)
      .filter(([key]) => key.startsWith(prefix)).map(([key, location]) => {
        const identity = JSON.stringify(location);
        let cached = this.cache.get(key);
        if (cached?.location !== identity) {
          cached = { location: identity, value: this.readLocation(location) };
          this.cache.set(key, cached);
        }
        return [key, JSON.parse(cached!.value)];
      }));
  }

  write(values: Record<string, unknown>, replacePrefix?: string) {
    const previous = this.manifest();
    const records = { ...previous.records };
    const pendingCache = new Map<string, { location: string; value: string }>();
    let row = previous.next;
    const append = (raw: string): Location => {
      const first = row;
      for (let offset = 0; offset < raw.length; offset += RECORD_CHUNK_SIZE) {
        const chunk = raw.slice(offset, offset + RECORD_CHUNK_SIZE);
        this.cells.write(row, chunk);
        if (this.cells.read(row) !== chunk) throw new Error(`隐藏元数据第 ${row} 行写入核对失败`);
        row += 1;
      }
      return { row: first, count: row - first };
    };
    if (replacePrefix) {
      Object.keys(records).filter((key) => key.startsWith(replacePrefix) && !(key in values))
        .forEach((key) => { delete records[key]; });
    }
    for (const [key, value] of Object.entries(values)) {
      const raw = JSON.stringify(value);
      const old = previous.records[key];
      const cached = this.cache.get(key);
      if (old && (cached?.location === JSON.stringify(old)
        ? cached.value : this.readLocation(old)) === raw) continue;
      records[key] = append(raw);
      pendingCache.set(key, { location: JSON.stringify(records[key]), value: raw });
    }
    // All data precedes the single-cell pointer flip; failed writes leave the old root readable.
    const indexRow = row;
    let next = row + 1;
    let raw = '';
    for (;;) {
      raw = JSON.stringify({ format: 'presales-records-v2', next, records });
      const actual = indexRow + Math.ceil(raw.length / RECORD_CHUNK_SIZE);
      if (actual === next) break;
      next = actual;
    }
    const manifest = append(raw);
    const header = JSON.stringify({ schema_version: 2, format: 'presales-records-v2', manifest });
    this.cells.write(1, header);
    if (this.cells.read(1) !== header) throw new Error('隐藏元数据根索引写入核对失败');
    // Unpublished row locations may be reused by another page after a failed root write.
    for (const [key, value] of pendingCache) this.cache.set(key, value);
  }
}

export function readMetadataRecords(store: MetadataRecords): WorkbookMetadata {
  const records = store.records('meta/');
  const base = records['meta/base'] as WorkbookMetadata;
  if (!base || base.schema_version !== 2 || !base.workbook_instance_id) {
    throw new Error('工作簿 v2 元数据缺少身份');
  }
  return { ...base, line_bindings: Object.entries(records)
    .filter(([key]) => key.startsWith('meta/line/')).map(([, value]) => value as WorkbookMetadata['line_bindings'][number]) };
}

export function writeMetadataRecords(store: MetadataRecords, metadata: WorkbookMetadata) {
  const { line_bindings, ...base } = metadata;
  store.write({ 'meta/base': base, ...Object.fromEntries(
    line_bindings.map((line) => [`meta/line/${line.line_id}`, line]),
  ) }, 'meta/');
}
