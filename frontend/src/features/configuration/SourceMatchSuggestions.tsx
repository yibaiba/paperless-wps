import { Button, Space, Tag, Typography } from "antd";

export interface MatchSourceRef {
  id: string;
  sheet: string;
  row: number;
}

export interface MatchSuggestion {
  variant_id: string;
  variant_name: string;
  product_model: string;
  product_name: string;
  match_type: "exact" | "source_variance" | "conflict";
  differences: string[];
  best_source: MatchSourceRef;
  source_refs: MatchSourceRef[];
}

const differenceLabels: Record<string, string> = {
  model: "型号",
  name: "名称",
  brand: "品牌",
  category: "类别",
  specification: "完整参数",
  short_specification: "简略参数",
  tender_specification: "招标参数",
  note: "备注",
  unit: "单位",
  prices: "价格",
  hidden: "隐藏状态",
};

const matchLabels = {
  exact: { label: "字段完全一致", color: "green" },
  source_variance: { label: "仅来源差异", color: "blue" },
  conflict: { label: "存在配置差异", color: "orange" },
} as const;

export function suggestedEvidence(suggestion: MatchSuggestion) {
  const source = `${suggestion.best_source.sheet} 第 ${suggestion.best_source.row} 行`;
  if (!suggestion.differences.length) {
    return `候选配置与当前来源字段完全一致，参照 ${source}；请维护者核对后确认归属。`;
  }
  const differences = suggestion.differences
    .map((field) => differenceLabels[field] ?? field)
    .join("、");
  return `候选配置参照 ${source}，差异字段：${differences}；请维护者核对后确认是否属于同一配置。`;
}

export function SourceMatchSuggestions({
  suggestions,
  onLink,
}: {
  suggestions: MatchSuggestion[];
  onLink: (suggestion: MatchSuggestion) => void;
}) {
  if (!suggestions.length) {
    return <Typography.Text type="secondary">没有同型号已确认配置</Typography.Text>;
  }
  return (
    <Space orientation="vertical" size={8} className="source-match-list">
      {suggestions.map((suggestion) => {
        const match = matchLabels[suggestion.match_type];
        return (
          <div className="source-match-item" key={suggestion.variant_id}>
            <Space size={4} wrap>
              <Tag color={match.color}>{match.label}</Tag>
              <Button type="link" size="small" onClick={() => onLink(suggestion)}>
                {suggestion.product_model} · {suggestion.variant_name}
              </Button>
            </Space>
            <Typography.Text type="secondary" className="source-match-detail">
              {suggestion.differences.length
                ? `差异：${suggestion.differences
                    .map((field) => differenceLabels[field] ?? field)
                    .join("、")}`
                : "产品与来源字段一致"}
              {`；参照 ${suggestion.best_source.sheet} 第 ${suggestion.best_source.row} 行`}
            </Typography.Text>
          </div>
        );
      })}
    </Space>
  );
}
