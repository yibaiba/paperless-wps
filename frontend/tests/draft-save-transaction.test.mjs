import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSaveTransaction } from '../src/features/configuration/projects/drafts/saveTransaction.ts';

function scenario(failure) {
  let workspace = { id: 'draft', revision: 1, base_revision: 0, configuration: { note: 'A' } };
  let remote = structuredClone(workspace), project, failed = false, writes = 0, serial = 0;
  const receipts = new Map();
  function fault(phase) {
    if (!failed && failure === phase) { failed = true; throw new Error('injected ' + phase); }
  }
  const transaction = createSaveTransaction({
    newId: () => String(++serial),
    isRejected: (cause) => cause.status === 409 || cause.status === 422,
    async post(path, request) {
      const kind = path.endsWith('list_check') ? 'check' : 'save';
      fault(kind + '-before');
      if (!failed && failure === kind + '-rejected') {
        failed = true; throw Object.assign(new Error('rejected ' + kind), { status: 409 });
      }
      if (receipts.has(request.operation_id)) return structuredClone(receipts.get(request.operation_id));
      assert.equal(request.expected_revision, workspace.revision);
      let result;
      if (kind === 'check') result = { revision: ++workspace.revision, check_fingerprint: 'checked' };
      else {
        assert.equal(request.expected_project_revision, workspace.base_revision);
        project = { revision: ++workspace.base_revision, configuration: structuredClone(workspace.configuration) };
        result = { revision: ++workspace.revision, project_revision: project.revision };
        writes++;
      }
      receipts.set(request.operation_id, structuredClone(result));
      fault(kind + '-after');
      return result;
    },
    async readWorkspace() { fault('workspace-read'); return structuredClone(workspace); },
    async readProject() { fault('project-read'); return structuredClone(project); },
    acceptWorkspace(value) { remote = value; },
  });
  return {
    transaction, remote: () => remote, writes: () => writes,
    edit(note) { workspace = { ...workspace, revision: workspace.revision + 1, configuration: { note } }; remote = structuredClone(workspace); },
    externalSave() { project = { ...project, revision: project.revision + 1 }; },
  };
}

for (const phase of ['check-before', 'check-after', 'save-before', 'save-after', 'workspace-read', 'project-read']) {
  test(`uncertain ${phase}: retry commits once`, async () => {
    const s = scenario(phase);
    await assert.rejects(s.transaction.save(s.remote()), /injected/);
    await s.transaction.settle();
    const result = await s.transaction.save(s.remote());
    assert.equal(result.configuration.note, 'A');
    assert.equal(s.writes(), 1);
  });
  test(`edit after ${phase}: previous receipt never substitutes for the new save`, async () => {
    const s = scenario(phase);
    await assert.rejects(s.transaction.save(s.remote()), /injected/);
    // The hook settles uncertain writes before it sends any new edit.
    await s.transaction.settle();
    s.edit('B');
    const result = await s.transaction.save(s.remote());
    assert.equal(result.configuration.note, 'B');
    assert.equal(result.revision, 2);
    assert.equal(s.writes(), 2);
  });
}
test('a later project save cannot masquerade as the acknowledged revision', async () => {
  const s = scenario('project-read');
  await assert.rejects(s.transaction.save(s.remote()), /injected/);
  s.externalSave();
  await assert.rejects(s.transaction.save(s.remote()), /其他保存版本/);
  assert.equal(s.writes(), 1);
});

for (const phase of ['check', 'save']) {
  test(`${phase} rejected: expose the conflict and permit subsequent draft edits`, async () => {
    const s = scenario(phase + '-rejected');
    await assert.rejects(s.transaction.save(s.remote()), /rejected/);
    await s.transaction.settle();
    s.edit('corrected B');
    const result = await s.transaction.save(s.remote());
    assert.equal(result.configuration.note, 'corrected B');
    assert.equal(s.writes(), 1);
  });
}
