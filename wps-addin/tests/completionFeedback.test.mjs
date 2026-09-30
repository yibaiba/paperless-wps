import assert from 'node:assert/strict';
import { test } from 'node:test';

import { completionFeedbackPayload } from '../src/completionFeedback.ts';

test('accepted completion reports the prior product and skipped first choice', () => {
  const first = { variant_id: 'suggested', source_id: 'source-1' };
  const chosen = { variant_id: 'chosen', source_id: 'source-2' };
  const payload = completionFeedbackPayload({
    operationId: 'operation',
    context: {
      profile: { id: 'profile', revision: 3 },
      cell: { sheet: '报价表' },
    },
    metadata: { workbook_instance_id: 'workbook' },
    productContext: {
      section: '会议系统',
      previous_variant_ids: ['previous', 'older'],
      next_variant_ids: ['following'],
    },
    query: '',
    candidates: [first, chosen],
    chosen,
  });

  assert.deepEqual(payload, {
    operation_id: 'operation',
    workbook_instance_id: 'workbook',
    template_profile_id: 'profile',
    template_profile_revision: 3,
    sheet: '报价表',
    section: '会议系统',
    previous_variant_id: 'previous',
    context_previous_variant_ids: ['previous', 'older'],
    context_next_variant_ids: ['following'],
    suggested_variant_id: 'suggested',
    chosen_variant_id: 'chosen',
    chosen_source_id: 'source-2',
    query_kind: 'contextual',
  });
});

test('typed completion is distinguished from contextual Tab acceptance', () => {
  const chosen = { variant_id: 'chosen', source_id: 'source' };
  const payload = completionFeedbackPayload({
    operationId: 'operation',
    context: { profile: { id: 'profile', revision: 1 }, cell: { sheet: '报价表' } },
    metadata: { workbook_instance_id: 'workbook' },
    productContext: { section: '', previous_variant_ids: ['previous'], next_variant_ids: [] },
    query: '产品名称',
    candidates: [chosen],
    chosen,
  });

  assert.equal(payload.query_kind, 'typed');
  assert.equal(payload.previous_variant_id, 'previous');
});

test('first product does not report an unusable transition', () => {
  const chosen = { variant_id: 'chosen', source_id: 'source' };
  const payload = completionFeedbackPayload({
    operationId: 'operation',
    context: { profile: { id: 'profile', revision: 1 }, cell: { sheet: '报价表' } },
    metadata: { workbook_instance_id: 'workbook' },
    productContext: { section: '', previous_variant_ids: [], next_variant_ids: [] },
    query: '',
    candidates: [chosen],
    chosen,
  });

  assert.equal(payload, null);
});
