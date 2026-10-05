import type { DiagnosticEventPayload } from './types';

export interface DiagnosticEventStore {
  put(events: readonly DiagnosticEventPayload[]): Promise<void>;
  list(options?: { eventIds?: readonly string[]; limit?: number }): Promise<DiagnosticEventPayload[]>;
  remove(eventIds: readonly string[]): Promise<void>;
}

export const DIAGNOSTIC_BATCH_SIZE = 50;
const DATABASE_NAME = 'presales-diagnostics';
const DATABASE_VERSION = 1;
const STORE = 'events';

export class IndexedDbDiagnosticStore implements DiagnosticEventStore {
  private connection?: Promise<IDBDatabase>;
  private readonly factory: () => IDBFactory | undefined;
  private readonly name: string;
  constructor(options: { factory: () => IDBFactory | undefined; name?: string }) {
    this.factory = options.factory; this.name = options.name ?? DATABASE_NAME;
  }
  private open() {
    if (this.connection) return this.connection;
    this.connection = new Promise<IDBDatabase>((resolve, reject) => {
      const factory = this.factory();
      if (!factory) throw new Error('WPS 诊断 IndexedDB 不可用；事件未能保存');
      const request = factory.open(this.name, DATABASE_VERSION);
      let blocked = false;
      request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'event_id' });
      request.onblocked = () => { blocked = true; reject(new Error('WPS 诊断数据库升级被其他窗口阻塞')); };
      request.onerror = () => reject(request.error ?? new Error('WPS 诊断数据库打开失败'));
      request.onsuccess = () => {
        const database = request.result;
        if (blocked) { database.close(); return; }
        database.onversionchange = () => { database.close(); this.connection = undefined; };
        resolve(database);
      };
    }).catch((error) => { this.connection = undefined; throw error; });
    return this.connection;
  }
  private async transaction<T>(options: {
    mode: IDBTransactionMode; run: (store: IDBObjectStore, result: (value: T) => void) => void;
  }): Promise<T> {
    const database = await this.open();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE, options.mode);
      let value: T;
      transaction.oncomplete = () => resolve(value);
      transaction.onabort = () => reject(transaction.error ?? new Error('WPS 诊断事务被中止'));
      transaction.onerror = () => reject(transaction.error ?? new Error('WPS 诊断事件保存失败'));
      options.run(transaction.objectStore(STORE), (result) => { value = result; });
    });
  }
  put(events: readonly DiagnosticEventPayload[]) {
    return this.transaction<void>({ mode: 'readwrite', run: (store) => {
      for (const event of events) {
        const existing = store.get(event.event_id);
        // Read/write transactions serialize across windows. Keep the first
        // delivery of an operation instead of overwriting its original outcome.
        existing.onsuccess = () => { if (!existing.result) store.add(event); };
      }
    } });
  }
  list(options: { eventIds?: readonly string[]; limit?: number } = {}) {
    return this.transaction<DiagnosticEventPayload[]>({ mode: 'readonly', run: (store, result) => {
      const events: DiagnosticEventPayload[] = [];
      result(events);
      if (options.eventIds) {
        for (const id of options.eventIds) {
          const request = store.get(id);
          request.onsuccess = () => { if (request.result) events.push(request.result); };
        }
        return;
      }
      const request = store.openCursor();
      request.onsuccess = () => {
        const cursor = request.result;
        if (!cursor || events.length >= (options.limit ?? DIAGNOSTIC_BATCH_SIZE)) return;
        events.push(cursor.value); cursor.continue();
      };
    } });
  }
  remove(eventIds: readonly string[]) {
    return this.transaction<void>({ mode: 'readwrite', run: (store) => {
      eventIds.forEach((id) => store.delete(id));
    } });
  }
  async close() { (await this.connection)?.close(); this.connection = undefined; }
}
