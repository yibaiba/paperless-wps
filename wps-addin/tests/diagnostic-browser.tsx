// Test-only entry. Uses real browser IndexedDB, no production workbook or token.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { DiagnosticRecorder, DIAGNOSTIC_OUTBOX_KEY } from '../src/diagnostics';
import { IndexedDbDiagnosticStore } from '../src/diagnosticStore';
import { businessDiagnostic } from '../src/businessDiagnostics';
import '../src/styles.css';

const COUNT = 40;
function check(value: boolean, message: string) { if (!value) throw new Error(message); }
async function run() {
  const name = `wps-diagnostic-test-${crypto.randomUUID()}`;
  const stores = [0, 1].map(() => new IndexedDbDiagnosticStore({ factory: () => indexedDB, name }));
  const legacy = new Map<string, string>();
  const make = (store: IndexedDbDiagnosticStore) => new DiagnosticRecorder({ store,
    get: (key) => legacy.get(key) ?? null, set: (key, value) => { legacy.set(key, value); },
    remove: (key) => { legacy.delete(key); }, installationId: () => 'isolated-browser-test',
    hostOs: () => navigator.platform, hostVersion: () => 'browser-not-wps' });
  const recorders = stores.map(make);
  const samples: number[] = [];
  try {
    const seed = await recorders[0].record({ event_type: 'inline_open', event_id: 'legacy' });
    await stores[0].remove(['legacy']); legacy.set(DIAGNOSTIC_OUTBOX_KEY, JSON.stringify([seed]));
    const migrated = make(stores[0]);
    await migrated.pending(); check(!legacy.has(DIAGNOSTIC_OUTBOX_KEY), '迁移未清理旧队列');
    const events = await Promise.all(Array.from({ length: COUNT }, (_, i) => {
      const start = performance.now();
      const pending = recorders[i % 2].record({ event_type: 'query_success', event_id: `event-${i}` });
      samples.push(performance.now() - start); return pending;
    }));
    check((await stores[0].list()).length === COUNT + 1, '双连接写入丢失事件');
    await recorders[0].remove(events.slice(0, COUNT / 2).map((event) => event.event_id));
    check((await stores[1].list()).length === COUNT / 2 + 1, '上传删除覆盖了其他连接事件');
    let error = '';
    businessDiagnostic({ recordDiagnostic: async () => { throw new Error('隔离故障注入'); },
      reportBackgroundError: (value) => { error = value; } }, { event_type: 'query_start' });
    await new Promise<void>((resolve) => queueMicrotask(resolve));
    check(error.includes('隔离故障注入'), '异步失败未显示');
    samples.sort((a, b) => a - b);
    return { status: 'passed', native_host_verified: false, migration: 'passed',
      concurrent_connections: 2, concurrent_events: COUNT, remaining_events: COUNT / 2 + 1,
      asynchronous_failure: 'visible', enqueue_call_p95_ms: samples[Math.ceil(COUNT * .95) - 1] };
  } finally { await Promise.all(stores.map((store) => store.close())); }
}

async function sharedWindow(write: boolean) {
  const params = new URLSearchParams(location.search);
  const name = params.get('database') ?? '';
  const writer = params.get('writer') ?? '';
  check(/^wps-diagnostic-test-[a-f0-9-]+$/.test(name) && ['A', 'B'].includes(writer), '隔离数据库参数不正确');
  const store = new IndexedDbDiagnosticStore({ factory: () => indexedDB, name });
  const storage = new Map<string, string>();
  const recorder = new DiagnosticRecorder({ store, get: (k) => storage.get(k) ?? null,
    set: (k, v) => { storage.set(k, v); }, remove: (k) => { storage.delete(k); },
    installationId: () => 'isolated-cross-page', hostOs: () => navigator.platform,
    hostVersion: () => 'browser-not-wps' });
  try {
    if (write) await Promise.all(Array.from({ length: COUNT / 2 }, (_, i) =>
      recorder.record({ event_type: 'query_success', event_id: `${writer}-${i}` })));
    return { writer, written_this_page: write ? COUNT / 2 : 0,
      shared_queue_count: (await store.list()).length, native_host_verified: false };
  } finally { await store.close(); }
}

function Harness() {
  const [result, setResult] = useState<unknown>('未执行');
  return <main style={{ padding: 24, maxWidth: 700 }}>
    <h1>真实 IndexedDB · 浏览器隔离验证</h1>
    <p>运行实际异步队列：旧记录迁移、双连接并发、上传删除和错误显示。不是 WPS 真机测试。</p>
    <button onClick={() => { setResult('运行中'); run().then(setResult).catch((error) => setResult({ status: 'failed', error: String(error) })); }}>运行异步诊断验证</button>
    {location.search && <><button onClick={() => sharedWindow(true).then(setResult).catch((e) => setResult(String(e)))}>写入当前测试页面 20 个事件</button>
      <button onClick={() => sharedWindow(false).then(setResult).catch((e) => setResult(String(e)))}>读取共享队列</button></>}
    <pre role="status">{JSON.stringify(result, null, 2)}</pre>
  </main>;
}
createRoot(document.getElementById('root')!).render(<Harness />);
