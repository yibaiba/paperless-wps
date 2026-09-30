import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  candidateIsAmbiguous,
  completionCommand,
  completionKey,
  navigateCandidates,
  selectionForCandidates,
  suggestionDelay,
} from '../src/completionState.ts';

function candidate(overrides = {}) {
  return {
    key: 'v1:s1',
    model: 'CRIR-D-OA',
    name: '对接OA系统',
    variant_id: 'v1',
    source_id: 's1',
    confidence: 'high',
    completion_ready: true,
    ...overrides,
  };
}

test('a unique prefix or contextual ghost accepts with one Tab', () => {
  const candidates = [candidate()];
  const prefix = selectionForCandidates('对接OA', candidates);
  const contextual = selectionForCandidates('', candidates);
  assert.equal(prefix.expanded, false);
  assert.equal(contextual.expanded, false);
  assert.equal(completionCommand({
    key: 'Tab', candidates, selection: prefix, hasGhost: true,
  }), 'accept');
});

test('only high-confidence candidates become one-key ghost completions', () => {
  const candidates = [candidate({ confidence: 'low' })];
  const selection = selectionForCandidates('', candidates);
  assert.equal(selection.expanded, true);
  assert.equal(completionCommand({
    key: 'Tab', candidates, selection, hasGhost: false,
  }), 'expand');
});

test('a high-confidence result without enough ranking margin requires a choice', () => {
  const candidates = [candidate({ completion_ready: false }), candidate({
    key: 'v2:s2', variant_id: 'v2', model: 'CRIR-D-WE', name: '对接微信',
  })];
  const selection = selectionForCandidates('', candidates);
  assert.equal(selection.expanded, true);
  assert.equal(completionCommand({
    key: 'Tab', candidates, selection, hasGhost: false,
  }), 'expand');
});

test('an exact unique name fills the row with one Tab', () => {
  const candidates = [candidate()];
  const selection = selectionForCandidates('对接OA系统', candidates);
  assert.equal(selection.expanded, false);
  assert.equal(completionCommand({
    key: 'Tab', candidates, selection, hasGhost: true, query: '对接OA系统',
  }), 'accept');
});

test('an exact shared name requires choosing the concrete model', () => {
  const candidates = [
    candidate({ model: 'SERVER-A', name: '服务器' }),
    candidate({ key: 'v2:s2', variant_id: 'v2', model: 'SERVER-B', name: '服务器' }),
  ];
  const selection = selectionForCandidates('服务器', candidates);
  assert.equal(candidateIsAmbiguous(candidates, 0, '服务器'), true);
  assert.equal(selection.expanded, true);
  assert.equal(completionCommand({
    key: 'Tab', candidates, selection, hasGhost: true, query: '服务器',
  }), 'expand');
});

test('an exact unique model stays unambiguous when product names are shared', () => {
  const candidates = [
    candidate({ model: 'SERVER-A', name: '服务器' }),
    candidate({ key: 'v2:s2', variant_id: 'v2', model: 'SERVER-B', name: '服务器' }),
  ];
  const selection = selectionForCandidates('SERVER-A', candidates, 'model');
  assert.equal(candidateIsAmbiguous(candidates, 0, 'SERVER-A'), false);
  assert.equal(selection.expanded, false);
});

test('contextual next-row prediction starts immediately while typing remains debounced', () => {
  assert.equal(suggestionDelay(''), 0);
  assert.equal(suggestionDelay('CRIR'), 150);
});

test('multiple concrete configurations require an explicit choice', () => {
  const candidates = [
    candidate({ completion_ready: false }),
    candidate({ key: 'v2:s2', variant_id: 'v2', source_id: 's2', completion_ready: false }),
  ];
  const selection = selectionForCandidates('对接OA', candidates);
  assert.equal(candidateIsAmbiguous(candidates), true);
  assert.equal(selection.expanded, true);
  assert.equal(completionCommand({
    key: 'Tab', candidates, selection, hasGhost: true,
  }), 'expand');
  assert.equal(completionCommand({
    key: 'Enter', candidates, selection, hasGhost: true,
  }), 'accept');
  const explicit = navigateCandidates(selection, candidates.length, 1);
  assert.equal(explicit.explicit, true);
  assert.equal(completionCommand({
    key: 'Tab', candidates, selection: explicit, hasGhost: true,
  }), 'accept');
});

test('an exact source-context match can resolve cross-template configurations', () => {
  const candidates = [
    candidate(),
    candidate({
      key: 'v2:s2', variant_id: 'v2', source_id: 's2', completion_ready: false,
    }),
  ];

  assert.equal(candidateIsAmbiguous(candidates), false);
  assert.equal(candidateIsAmbiguous(candidates, 0, 'CRIR-D-OA'), false);
  assert.equal(selectionForCandidates('', candidates).expanded, false);
});

test('fuzzy results expand and an empty result restores native Tab', () => {
  const candidates = [candidate()];
  const selection = selectionForCandidates('OA', candidates);
  assert.equal(selection.expanded, true);
  assert.equal(completionCommand({
    key: 'Tab', candidates, selection, hasGhost: false,
  }), 'expand');
  assert.equal(completionCommand({
    key: 'Tab', candidates: [], selection, hasGhost: false,
  }), 'native-tab');
});

test('IME composition suppresses completion keys while Escape and arrows remain explicit', () => {
  assert.equal(completionKey('Tab', true), null);
  assert.equal(completionKey('Enter', true), null);
  assert.equal(completionKey('a', false), null);
  assert.equal(completionKey('Escape', false), 'Escape');
  assert.equal(completionKey('ArrowDown', false), 'ArrowDown');
});
