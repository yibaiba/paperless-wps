import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function load(name, modules, window) {
  const file = new URL(`../src/features/configuration/projects/drafts/${name}.ts`, import.meta.url);
  const js = ts.transpileModule(readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports, crypto: globalThis.crypto, URLSearchParams, window,
    require(name) { assert.ok(name in modules, name); return modules[name]; },
  });
  return exports;
}

function scenario(failure) {
  const slots = [], effects = [], listeners = new Map(), sent = [], receipts = new Map();
  let cursor = 0, blocker, applied = 0, attempt = 0, creationAttempts = 0;
  const window = {
    addEventListener(name, fn) { listeners.set(name, fn); },
    removeEventListener(name, fn) { if (listeners.get(name) === fn) listeners.delete(name); },
  };
  const react = {
    useRef(value) { const i = cursor++; return slots[i] ??= { current: value }; },
    useReducer(reducer, initial) {
      const i = cursor++; if (!(i in slots)) slots[i] = initial;
      return [slots[i], action => { slots[i] = reducer(slots[i], action); }];
    },
    useState(value) {
      const i = cursor++; if (!(i in slots)) slots[i] = value;
      return [slots[i], v => { slots[i] = typeof v === 'function' ? v(slots[i]) : v; }];
    },
    useEffect(fn, deps) {
      const i = cursor++, old = slots[i];
      if (!old || deps.some((value, index) => value !== old.deps[index])) {
        effects.push(() => { old?.cleanup?.(); slots[i] = { deps, cleanup: fn() }; });
      }
    },
  };
  class ApiError extends Error { constructor(status) { super(`VERSION_CONFLICT ${status}`); this.status = status; } }
  let workspace = { id: 'draft', revision: 1, base_revision: 0, configuration: { note: 'old' } };
  workspace.checked = { configuration: workspace.configuration };
  const checkpoints = new Map([[1, structuredClone(workspace)]]);
  const options = {
    projectId: 'p', saved: { revision: 0, configuration: workspace.configuration },
    configuration: workspace.configuration,
    initialWorkspace: failure?.startsWith('create-') ? undefined : structuredClone(workspace),
    accept(checked) { options.configuration = checked.configuration; },
    acceptOperation(checked) { applied++; options.configuration = checked.configuration; },
    acceptCheckpoint(checked, key) { applied++; options.configuration = checked.configuration; options.historyKey = key; },
  };
  async function post(path, request) {
    sent.push(structuredClone(request));
    if (receipts.has(request.operation_id)) return structuredClone(receipts.get(request.operation_id));
    if (path === '/work-drafts') {
      creationAttempts++;
      if (failure === 'create-offline' && creationAttempts === 1) throw new Error(failure);
      receipts.set(request.operation_id, structuredClone(workspace));
      if (failure === 'create-ack-lost' && creationAttempts === 1) throw new Error(failure);
      return structuredClone(workspace);
    }
    assert.ok(['/edit', '/restore', '/recheck', '/check'].some(suffix => path.endsWith(suffix)), path);
    attempt++;
    if (failure === 'offline' && attempt === 1) throw new Error('offline');
    if (['rejected', 'conflict'].includes(failure) && attempt === 1) throw new ApiError(failure === 'rejected' ? 422 : 409);
    if (request.expected_revision !== workspace.revision) throw new ApiError(409);
    if (path.endsWith('/restore')) {
      workspace = { ...structuredClone(checkpoints.get(request.checkpoint_revision)), revision: workspace.revision + 1 };
    } else {
      const configuration = request.operations ? { note: request.operations[0].note } : workspace.configuration;
      workspace = { ...workspace, revision: workspace.revision + 1, configuration,
        checked: { configuration, ...(path.endsWith('/recheck') ? { usage_projection: { version: 1 } } : {}) } };
    }
    checkpoints.set(workspace.revision, structuredClone(workspace));
    receipts.set(request.operation_id, structuredClone(workspace));
    if (failure === 'ack-lost' && attempt === 1) throw new Error('ack-lost');
    return structuredClone(workspace);
  }
  const { usePersistentDraft } = load('usePersistentDraft', {
    react, 'react-router-dom': {
      useBlocker(predicate) { blocker = predicate; return { state: 'unblocked' }; },
      useSearchParams: () => [null, () => {}],
    },
    antd: { App: { useApp: () => ({ modal: {} }) } },
    '../../../../shared/api': { api: async () => { throw new Error('Unexpected read'); }, ApiError },
    './operations': { configurationOperations: (_, after) => [{ action: 'device_patch', note: after.note }] },
    './transport': { post, mergeDelta: (_, delta) => delta,
      writeRequest: (state, operations) => ({ draft_id: state.id, expected_revision: state.revision, operation_id: crypto.randomUUID(), operations }) },
    '../configurationIdentity': { configurationKey: JSON.stringify },
    './saveTransaction': load('saveTransaction', {}, window),
  }, window);
  return {
    sent, options, revision: () => workspace.revision, applied: () => applied,
    render() { cursor = 0; const result = usePersistentDraft(options); while (effects.length) effects.shift()(); return result; },
    leaving() { return blocker({ currentLocation: {pathname: '/configuration/p'}, nextLocation: {pathname: '/projects'}, historyAction: 'PUSH' }); },
    closing() { let prevented = false; listeners.get('beforeunload')?.({preventDefault() {prevented = true;}}); return prevented; },
  };
}

for (const failure of [undefined, 'ack-lost']) {
  test(`recheck of unchanged facts restores the original check checkpoint (${failure ?? 'success'})`, async () => {
    const s = scenario(failure), first = s.render();
    const adoption = { expected_project_revision: 0, fingerprint: 'preview', refresh_knowledge: false,
      upgrade_calculation: false, upgrade_decisions: false, cleanup_allocations: false };
    if (failure) {
      await assert.rejects(first.recheck(adoption), /ack-lost/);
      await s.render().retry();
    } else await first.recheck(adoption);
    assert.equal(s.options.configuration.note, 'old');
    assert.equal(s.applied(), 1);
    const token = s.options.historyKey, state = s.render();
    assert.match(token, /^workspace:draft:2$/);
    assert.equal(state.unsynced, false);
    s.options.historyKey = '';
    await state.retry();
    assert.equal(s.sent.at(-1).checkpoint_revision, 1, 'the old check must not be overwritten by the new check');
    const undo = s.render();
    s.options.historyKey = token;
    await undo.retry();
    assert.equal(s.sent.at(-1).checkpoint_revision, 2);
    assert.equal(s.render().unsynced, false);
  });
}

for (const failure of ['offline', 'ack-lost']) {
  test(`pending ${failure} operation remains protected and retries with its original identity`, async () => {
    const s = scenario(failure);
    await assert.rejects(s.render().execute([{action: 'device_patch', note: 'new'}]), new RegExp(failure));
    const failed = s.render();
    assert.equal(failed.unsynced, true, 'unacknowledged operation is unsynced even before local projection changes');
    assert.equal(s.leaving(), true);
    assert.equal(s.closing(), true);
    assert.equal(failed.canDiscardRejected, false, 'an uncertain write must retain its original retry');
    assert.throws(() => failed.discardRejected(), /未通过校验/);
    await failed.retry();
    const restored = s.render();
    assert.equal(restored.unsynced, false);
    assert.equal(s.leaving(), false);
    assert.equal(s.closing(), false);
    assert.equal(s.sent[0].operation_id, s.sent[1].operation_id);
    assert.equal(s.revision(), 2);
    assert.equal(s.applied(), 1);
    assert.equal(s.options.configuration.note, 'new');
  });
}

for (const failure of [undefined, 'ack-lost']) {
  test(`workspace check persists and adopts the summary projection (${failure ?? 'success'})`, async () => {
    const s = scenario(failure);
    const first = s.render();
    if (failure) {
      await assert.rejects(first.check(false), /ack-lost/);
      await s.render().retry();
    } else {
      await first.check(false);
    }
    const checkedRequest = s.sent.find(request => 'refresh_knowledge' in request);
    assert.equal(checkedRequest.refresh_knowledge, false);
    assert.equal(s.render().unsynced, false);
    assert.equal(s.revision(), 2);
  });
}

test('explicitly discard a rejected local projection without another write, then continue editing', async () => {
  const s = scenario('rejected');
  const initial = s.render();
  s.options.configuration = { note: 'invalid local edit' };
  await initial.retry();
  const failed = s.render();
  assert.equal(failed.canDiscardRejected, true);
  assert.equal(s.options.configuration.note, 'invalid local edit', 'failure alone must not discard input');
  failed.discardRejected();
  const recovered = s.render();
  assert.equal(recovered.unsynced, false);
  assert.equal(recovered.error, '');
  assert.equal(s.options.configuration.note, 'old');
  assert.equal(s.sent.length, 1);
  assert.equal(s.revision(), 1);
  assert.equal(s.closing(), false);
  const checked = await recovered.execute([{ action: 'device_patch', note: 'valid correction' }]);
  assert.equal(checked.configuration.note, 'valid correction');
  assert.equal(s.revision(), 2);
});

test('a version conflict or later local edit cannot be discarded as the rejected projection', async () => {
  for (const failure of ['conflict', 'rejected']) {
    const s = scenario(failure);
    const initial = s.render();
    s.options.configuration = { note: 'first edit' };
    await initial.retry();
    if (failure === 'rejected') s.options.configuration = { note: 'later edit' };
    const failed = s.render();
    assert.equal(failed.canDiscardRejected, false);
    assert.throws(() => failed.discardRejected(), /未通过校验/);
    assert.equal(s.revision(), 1);
  }
});

test('two simultaneous business edits cannot both reserve the same draft revision', async () => {
  const s = scenario();
  const state = s.render();
  const results = await Promise.allSettled([
    state.execute([{action: 'device_patch', note: 'first'}]),
    state.execute([{action: 'device_patch', note: 'second'}]),
  ]);
  assert.equal(s.sent.length, 1, 'only one operation may enter the transport');
  assert.equal(results.filter(r => r.status === 'fulfilled').length, 1);
  assert.equal(s.revision(), 2);
});

for (const failure of ['create-offline', 'create-ack-lost']) {
  test(`first edit survives ${failure} before the work draft is available`, async () => {
    const s = scenario(failure);
    await assert.rejects(s.render().execute([{action: 'device_patch', note: 'first edit'}]), new RegExp(failure));
    const failed = s.render();
    assert.equal(failed.unsynced, true);
    assert.equal(s.leaving(), true);
    await failed.retry();
    assert.equal(s.render().unsynced, false);
    assert.equal(s.options.configuration.note, 'first edit');
    assert.equal(s.revision(), 2);
    assert.equal(s.applied(), 1);
    const creation = s.sent.filter(r => !r.operations);
    assert.equal(creation.length, 2);
    assert.equal(creation[0].operation_id, creation[1].operation_id);
  });
}
