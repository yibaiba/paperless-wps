import type { SuggestionFeedbackPayload } from './types';

function optionalString(value: unknown) {
  return value === undefined || typeof value === 'string';
}

function optionalStringArray(value: unknown) {
  return value === undefined
    || (Array.isArray(value) && value.every((item) => typeof item === 'string'));
}

function isFeedback(value: unknown): value is SuggestionFeedbackPayload {
  if (!value || typeof value !== 'object') return false;
  const item = value as Record<string, unknown>;
  const strings = [
    'operation_id', 'workbook_instance_id', 'template_profile_id', 'sheet', 'section',
    'chosen_variant_id', 'chosen_source_id', 'query_kind',
  ];
  return strings.every((key) => typeof item[key] === 'string')
    && Number.isInteger(item.template_profile_revision)
    && optionalString(item.previous_variant_id)
    && optionalString(item.suggested_variant_id)
    && optionalStringArray(item.context_previous_variant_ids)
    && optionalStringArray(item.context_next_variant_ids)
    && (item.query_kind === 'contextual' || item.query_kind === 'typed');
}

export function parseFeedbackOutbox(raw: string | null): SuggestionFeedbackPayload[] {
  if (!raw) return [];
  let value: unknown;
  try { value = JSON.parse(raw); }
  catch { throw new Error('产品顺序学习队列损坏，请联系管理员'); }
  if (!Array.isArray(value) || !value.every(isFeedback)) {
    throw new Error('产品顺序学习队列格式无效，请联系管理员');
  }
  return value.map((item) => ({
    ...item,
    context_previous_variant_ids: item.context_previous_variant_ids ?? [],
    context_next_variant_ids: item.context_next_variant_ids ?? [],
  }));
}

export function enqueueFeedback(
  raw: string | null,
  feedback: SuggestionFeedbackPayload,
) {
  const items = parseFeedbackOutbox(raw);
  if (items.some((item) => item.operation_id === feedback.operation_id)) return raw ?? '[]';
  return JSON.stringify([...items, feedback]);
}

export function removeFeedback(raw: string | null, operationId: string) {
  return JSON.stringify(
    parseFeedbackOutbox(raw).filter((item) => item.operation_id !== operationId),
  );
}
