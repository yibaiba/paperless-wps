import { Button, Card, Input, Select, Space, Statistic, Table, Tag, Typography } from "antd";
import { Status } from "../shared";
import { SourceMatchSuggestions, type MatchSuggestion } from "../SourceMatchSuggestions";
import type { CatalogAudit, CatalogAuditRow, CatalogAuditStatus } from "./types";

export function CatalogAuditSummary({ audit }: { audit?: CatalogAudit }) {
  return (
    <Card>
      <Space wrap size={32}>
        <Statistic title="全部来源" value={audit?.total ?? 0} />
        <Statistic title="已确认归属" value={audit?.organized ?? 0} />
        <Statistic title="明确阻塞" value={audit?.blocked ?? 0} />
        <Statistic title="未处理" value={audit?.pending ?? 0} />
        <Statistic title="涉及资料问题" value={audit?.conflicts ?? 0} />
      </Space>
    </Card>
  );
}

export function CatalogSourceAuditPanel({
  rows,
  loading,
  selected,
  search,
  status,
  onSelected,
  onSearch,
  onStatus,
  onLinkSelected,
  onIndependentSelected,
  onBlockSelected,
  onSelectPending,
  onSuggestedLink,
  onDetail,
  onHistory,
}: {
  rows?: CatalogAuditRow[];
  loading: boolean;
  selected: string[];
  search: string;
  status: CatalogAuditStatus;
  onSelected: (ids: string[]) => void;
  onSearch: (value: string) => void;
  onStatus: (value: CatalogAuditStatus) => void;
  onLinkSelected: () => void;
  onIndependentSelected: () => void;
  onBlockSelected: () => void;
  onSelectPending: () => void;
  onSuggestedLink: (row: CatalogAuditRow, suggestion: MatchSuggestion) => void;
  onDetail: (id: string) => void;
  onHistory: (id: string) => void;
}) {
  return (
    <Card>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="型号、名称、工作表"
          value={search}
          onChange={(event) => onSearch(event.target.value)}
        />
        <Select
          value={status}
          style={{ width: 150 }}
          onChange={onStatus}
          options={[
            { value: "all", label: "全部处理状态" },
            { value: "pending", label: "只看未处理" },
            { value: "blocked", label: "只看明确阻塞" },
          ]}
        />
        <Button disabled={!selected.length} onClick={onLinkSelected}>
          关联所选 {selected.length} 条来源
        </Button>
        <Button disabled={!selected.length} onClick={onIndependentSelected}>
          分别确认为独立配置
        </Button>
        <Button disabled={!selected.length} onClick={onBlockSelected}>
          标记明确阻塞
        </Button>
        <Button onClick={onSelectPending}>选择全部未整理</Button>
      </Space>
      <Table<CatalogAuditRow>
        rowKey="id"
        dataSource={rows}
        loading={loading}
        scroll={{ x: 1450 }}
        rowSelection={{
          selectedRowKeys: selected,
          preserveSelectedRowKeys: true,
          onChange: (keys) => onSelected(keys as string[]),
        }}
        columns={sourceColumns({ onSuggestedLink, onDetail, onHistory })}
      />
    </Card>
  );
}

function sourceColumns({
  onSuggestedLink,
  onDetail,
  onHistory,
}: {
  onSuggestedLink: (row: CatalogAuditRow, suggestion: MatchSuggestion) => void;
  onDetail: (id: string) => void;
  onHistory: (id: string) => void;
}) {
  return [
    {
      title: "产品",
      render: (_: unknown, row: CatalogAuditRow) => (
        <>
          <strong>{row.model}</strong>
          <div>{row.name}</div>
          {row.duplicate_model ? <Tag>同型号多来源，需核对</Tag> : null}
        </>
      ),
    },
    {
      title: "原始来源",
      render: (_: unknown, row: CatalogAuditRow) => `${row.sheet} · 第 ${row.row} 行`,
    },
    {
      title: "归属配置",
      render: (_: unknown, row: CatalogAuditRow) =>
        row.variant
          ? `${row.variant.product.model} / ${row.variant.name}`
          : row.blocked
            ? `明确阻塞：${row.block_reason}`
            : "未整理",
    },
    {
      title: "匹配候选",
      width: 390,
      render: (_: unknown, row: CatalogAuditRow) => {
        if (row.organized) return <Typography.Text type="secondary">已完成归属</Typography.Text>;
        if (row.blocked) {
          return <Typography.Text type="warning">等待补充资料后重新处理</Typography.Text>;
        }
        return (
          <SourceMatchSuggestions
            suggestions={row.match_suggestions}
            onLink={(suggestion) => onSuggestedLink(row, suggestion)}
          />
        );
      },
    },
    {
      title: "状态",
      render: (_: unknown, row: CatalogAuditRow) => (
        <Status value={row.organized ? "confirmed" : row.blocked ? "blocked" : "pending"} />
      ),
    },
    {
      title: "资料问题",
      render: (_: unknown, row: CatalogAuditRow) => row.review_summary.total,
    },
    {
      title: "操作",
      render: (_: unknown, row: CatalogAuditRow) => (
        <Space>
          <Button onClick={() => onDetail(row.id)}>查看原文</Button>
          <Button onClick={() => onHistory(row.id)}>处理历史</Button>
        </Space>
      ),
    },
  ];
}
