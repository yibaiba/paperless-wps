import type { ReviewStatus, ReviewSummary } from '../../shared/types';

export const reviewLabels: Record<ReviewStatus, string> = {
  pending: '待确认',
  confirmed_variant: '确认为不同配置',
  equivalent: '仅表述不同',
  source_error: '原资料有误待修订',
};

export const reviewColors: Record<ReviewStatus, string> = {
  pending: 'gold', confirmed_variant: 'blue', equivalent: 'cyan', source_error: 'red',
};

export function summaryText(summary: ReviewSummary): string {
  if (!summary.total) return '暂无差异记录';
  const parts = [];
  if (summary.pending) parts.push(`${summary.pending} 项待确认`);
  if (summary.source_error) parts.push(`${summary.source_error} 项原资料待修订`);
  return parts.length ? parts.join('，') : `${summary.total} 项差异已有结论`;
}
