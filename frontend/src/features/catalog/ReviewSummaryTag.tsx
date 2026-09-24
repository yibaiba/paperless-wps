import { Tag, Tooltip } from 'antd';
import type { ReviewSummary } from '../../shared/types';
import { summaryText } from './reviewLabels';

export function ReviewSummaryTag({ summary }: { summary: ReviewSummary }) {
  const color = summary.source_error ? 'red' : summary.pending ? 'gold' : undefined;
  return <Tooltip title="仅反映当前来源版本的资料差异处理情况，不代表完成产品或兼容性校验。">
    <Tag color={color}>{summaryText(summary)}</Tag>
  </Tooltip>;
}
