import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  enqueueFeedback, parseFeedbackOutbox, removeFeedback,
} from '../src/feedbackOutbox.ts';

const feedback = {
  operation_id: 'operation',
  workbook_instance_id: 'workbook',
  template_profile_id: 'profile',
  template_profile_revision: 1,
  sheet: '报价表',
  section: '会议系统',
  previous_variant_id: 'previous',
  context_previous_variant_ids: ['previous', 'older'],
  context_next_variant_ids: [],
  suggested_variant_id: 'suggested',
  chosen_variant_id: 'chosen',
  chosen_source_id: 'source',
  query_kind: 'contextual',
};

test('feedback outbox survives dialog teardown and de-duplicates operations', () => {
  const once = enqueueFeedback(null, feedback);
  const twice = enqueueFeedback(once, feedback);

  assert.deepEqual(parseFeedbackOutbox(twice), [feedback]);
  assert.deepEqual(parseFeedbackOutbox(removeFeedback(twice, 'operation')), []);
});

test('corrupt feedback outbox is surfaced instead of discarded', () => {
  assert.throws(() => parseFeedbackOutbox('{broken'), /队列损坏/);
  assert.throws(() => parseFeedbackOutbox('[{}]'), /格式无效/);
});

test('the prior outbox format is upgraded with an empty sequence context', () => {
  const legacy = { ...feedback };
  delete legacy.context_previous_variant_ids;
  delete legacy.context_next_variant_ids;

  const [upgraded] = parseFeedbackOutbox(JSON.stringify([legacy]));

  assert.deepEqual(upgraded.context_previous_variant_ids, []);
  assert.deepEqual(upgraded.context_next_variant_ids, []);
});
