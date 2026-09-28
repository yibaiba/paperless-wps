import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Select, Space, Table, Typography } from "antd";
import { api } from "../../../shared/api";
import { ROOT } from "../shared";
import type { BusinessChange } from "../types";

export function ProjectRevisionDiff({ projectId, revisions }: { projectId: string; revisions: number[] }) {
  const [base, setBase] = useState<number>(), [target, setTarget] = useState<number>();
  const compare = useMutation({ mutationFn: () => api<{ changes: BusinessChange[]; procurement_changes: BusinessChange[] }>(`${ROOT}/projects/${projectId}/compare`, { method: "POST", body: JSON.stringify({ base_revision: base, target_revision: target }) }) });
  const options = revisions.map((v) => ({ value: v, label: `v${v}` }));
  return <Space orientation="vertical" style={{ width: "100%", marginBottom: 16 }}>
    <Space><Select aria-label="改单基线版本" placeholder="修改前版本" value={base} onChange={setBase} options={options} style={{ width: 140 }} />
      <Select aria-label="改单目标版本" placeholder="修改后版本" value={target} onChange={setTarget} options={options} style={{ width: 140 }} />
      <Button disabled={!base || !target || base === target} onClick={() => compare.mutate()} loading={compare.isPending}>比较已保存版本</Button></Space>
    {compare.error ? <Alert type="error" title={compare.error.message} /> : null}
    {compare.data ? <Table rowKey={(c) => `${c.kind}:${c.id}`} size="small" dataSource={[...compare.data.changes, ...compare.data.procurement_changes]} columns={[
      { title: "改动对象", dataIndex: "kind" }, { title: "修改前", render: (_, c) => <Typography.Paragraph ellipsis={{ rows: 3, expandable: true }}>{JSON.stringify(c.before)}</Typography.Paragraph> },
      { title: "修改后", render: (_, c) => <Typography.Paragraph ellipsis={{ rows: 3, expandable: true }}>{JSON.stringify(c.after)}</Typography.Paragraph> },
    ]} /> : null}
  </Space>;
}
