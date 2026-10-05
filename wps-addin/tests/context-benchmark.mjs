// Generated 1,000-row load test, not real WPS host latency or business accuracy.
import { contextWorkload } from './context-workload.mjs';
import { completionRowCache } from '../src/businessWorkbook.ts';

const workload = contextWorkload();
const samples = 50;
const measure = (fn) => { const start = performance.now(); fn(); return performance.now() - start; };
const cold = measure(() => workload.request());
const warm = Array.from({ length: samples }, (_, i) => measure(() => workload.request(`m${i}`)));
const edit = Array.from({ length: samples }, (_, i) => measure(() => {
  workload.rows[i + 1].values = { ...workload.rows[i + 1].values, quantity: String(i + 2) };
  workload.index.changed({ sheet: 'q', row: i + 3, rowCount: 1, structural: false });
  workload.metadata.business.local_revision++;
  workload.request();
}));
const p95 = (values) => [...values].sort((a, b) => a - b)[Math.ceil(values.length * .95) - 1];
console.log(JSON.stringify({ workload: 'generated-1000-rows', host_verified: false,
  cold_ms: cold, warm_p95_ms: p95(warm), edited_p95_ms: p95(edit), samples,
  parsed_rows: completionRowCache(workload.index).parsedRows, ...workload.metrics }, null, 2));
