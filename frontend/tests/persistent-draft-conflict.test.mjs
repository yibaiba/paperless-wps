import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function load(name, modules) {
  const file = new URL(`../src/features/configuration/projects/drafts/${name}.ts`, import.meta.url);
  const js = ts.transpileModule(readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports, crypto: globalThis.crypto, URLSearchParams,
    require(name) { assert.ok(name in modules, name); return modules[name]; },
  });
  return exports;
}

function scenario({ conflictAt, rejectionStatus = 409, raceAfterSave = false }) {
  const slots = []; let cursor = 0;
  const react = {
    useRef(value) { const i = cursor++; return slots[i] ??= { current: value }; },
    useState(value) {
      const i = cursor++; if (!(i in slots)) slots[i] = value;
      return [slots[i], v => { slots[i] = typeof v === 'function' ? v(slots[i]) : v; }];
    },
    useEffect() {},
  };
  class ApiError extends Error { constructor(status) { super(`VERSION_CONFLICT ${status}`); this.status = status; } }
  const initial = { note: 'local A' }, clone = structuredClone;
  let workspace = { id: 'draft', revision: 1, base_revision: 0, configuration: initial, checked: { configuration: initial } };
  let saved, injected = false, writes = 0;
  const receipts = new Map();
  const options = { projectId: 'p', saved: { revision: 0, configuration: initial },
    configuration: initial, initialWorkspace: clone(workspace), accept() {}, acceptOperation() {},
  };
  function externalEdit() {
    workspace = { ...workspace, revision: workspace.revision + 1,
      configuration: { note: 'other editor B' }, checked: { configuration: { note: 'other editor B' } },
    };
  }
  async function post(path, request) {
    const phase = path.endsWith('list_check') ? 'check' : 'save';
    if (receipts.has(request.operation_id)) return clone(receipts.get(request.operation_id));
    if (phase === conflictAt && !injected) {
      injected = true;
      if (rejectionStatus === 409) externalEdit();
      throw new ApiError(rejectionStatus);
    }
    if (request.expected_revision !== workspace.revision) throw new ApiError(409);
    let result;
    if (phase === 'check') result = { revision: ++workspace.revision, check_fingerprint: 'checked' };
    else {
      saved = { revision: ++workspace.base_revision, configuration: clone(workspace.configuration) };
      result = { revision: ++workspace.revision, project_revision: saved.revision };
      writes++;
    }
    receipts.set(request.operation_id, clone(result));
    return result;
  }
  async function api(path) {
    if (path === '/configuration/projects/p') return clone(saved);
    assert.equal(path, '/work-drafts/draft');
    if (raceAfterSave && saved && !injected) { injected = true; externalEdit(); }
    return clone(workspace);
  }
  const { usePersistentDraft } = load('usePersistentDraft', {
    react, 'react-router-dom': { useBlocker: () => ({ state: 'unblocked' }), useSearchParams: () => [null, () => {}] },
    antd: { App: { useApp: () => ({ modal: {} }) } }, '../../../../shared/api': { api, ApiError },
    './operations': { configurationOperations: () => { throw new Error('Unexpected edit'); } },
    './transport': { post }, './saveTransaction': load('saveTransaction', {}),
  });
  return { writes: () => writes, local: () => options.configuration,
    render() { cursor = 0; return usePersistentDraft(options); },
  };
}

for (const conflictAt of ['check', 'save']) {
  test(`${conflictAt} conflict: immediate retry cannot save another editor configuration`, async () => {
    const s = scenario({ conflictAt });
    await assert.rejects(s.render().save(), /409/);
    await assert.rejects(s.render().save(), /409/);
    assert.equal(s.writes(), 0);
    assert.equal(s.local().note, 'local A');
  });
}

test('save validation rejection can retry using its own acknowledged check revision', async () => {
  const s = scenario({ conflictAt: 'save', rejectionStatus: 422 });
  await assert.rejects(s.render().save(), /422/);
  const result = await s.render().save();
  assert.equal(result.configuration.note, 'local A');
  assert.equal(s.writes(), 1);
});

test('edit after save acknowledgement cannot silently become the next local save baseline', async () => {
  const s = scenario({ raceAfterSave: true });
  const result = await s.render().save();
  assert.equal(result.configuration.note, 'local A');
  await assert.rejects(s.render().save(), /409/);
  assert.equal(s.writes(), 1);
});
