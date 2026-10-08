import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function scenario() {
  let release;
  const waiting = new Promise(resolve => { release = resolve; });
  const received = { checks: [], saved: [], warnings: [], replacements: [], savedKeys: [] };
  const configuration = { devices: [], drawing_xml: '' };
  const result = { configuration, usage_projection: { fingerprint: 'earlier-check' } };
  const draft = { current: { current: configuration }, currentHistoryKey: { current: 'earlier' },
    commit: value => received.replacements.push(value), replaceCurrent: value => received.replacements.push(value) };
  const options = { projectId: 'project', draft, savedJson: { current: '' },
    saveWorkspace: async () => { await waiting; return result; },
    checkWorkspace: async () => { await waiting; return result; },
    setSaved: value => received.saved.push(value), setChecked: value => received.checks.push(value),
    onSaved: key => received.savedKeys.push(key) };
  const modules = {
    '@tanstack/react-query': { useMutation: value => value,
      useQueryClient: () => ({ setQueryData() {}, invalidateQueries() {} }) },
    antd: { App: { useApp: () => ({ message: { warning: value => received.warnings.push(value), success() {} } }) } },
    '../../../shared/api': { api: async () => { await waiting; return result; } },
    '../shared': { ROOT: '/api/configuration' }, '../queryKeys': { configurationKeys: { project: id => [id] } },
    './configurationIdentity': { configurationKey: JSON.stringify },
  };
  const source = readFileSync(new URL('../src/features/configuration/projects/useProjectRequests.ts', import.meta.url), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports, structuredClone, require: name => modules[name] });
  return { draft, received, release, requests: exports.useProjectRequests(options) };
}

test('saving acknowledges the originating check checkpoint without replacing a later checkpoint', async () => {
  const s = scenario();
  const pending = s.requests.save.mutationFn();
  s.draft.currentHistoryKey.current = 'later';
  s.release();
  s.requests.save.onSuccess(await pending);
  assert.deepEqual(s.received.savedKeys, ['earlier']);
  assert.equal(s.received.saved.length, 1);
  assert.equal(s.received.checks.length, 0);
  assert.equal(s.received.replacements.length, 0);
  assert.equal(s.received.warnings.length, 1);
});

test('project requests delegate checks to the persistent workspace without a second adoption', async () => {
  const s = scenario();
  const pending = s.requests.check.mutationFn(false);
  s.draft.currentHistoryKey.current = 'later';
  s.release();
  await pending;
  assert.equal(s.received.checks.length, 0);
  assert.equal(s.received.replacements.length, 0);
});

test('the current check checkpoint still accepts its successful response', async () => {
  const s = scenario();
  const pending = s.requests.save.mutationFn();
  s.release();
  s.requests.save.onSuccess(await pending);
  assert.deepEqual(s.received.savedKeys, ['earlier']);
  assert.equal(s.received.checks.length, 1);
  assert.equal(s.received.replacements.length, 1);
});
