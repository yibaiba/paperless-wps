import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Input,
  Modal,
  Space,
  Table,
  Typography,
} from "antd";
import { api } from "../../shared/api";
import type { Knowledge } from "./types";
import { ROOT, Status } from "./shared";
import { KnowledgeEditor } from "./KnowledgeEditor";
import "./configuration.css";
import { KnowledgeBatch } from "./KnowledgeBatch";
const kinds = {
  suitability: "系统适用",
  accessory: "配套关系",
  sharing: "共用部署",
};
export default function KnowledgePage() {
  const [batchOpen, setBatchOpen] = useState(false),
    [history, setHistory] = useState<string>();
  const revisions = useQuery({
    queryKey: ["configuration", "history", history],
    enabled: !!history,
    queryFn: () => api<Record<string, unknown>[]>(ROOT + "/history/" + history),
  });
  const client = useQueryClient();
  const { message } = App.useApp();
  const [editing, setEditing] = useState<Knowledge | null>(),
    [selected, setSelected] = useState<string[]>([]),
    [search, setSearch] = useState("");
  const query = useQuery({
    queryKey: ["configuration", "knowledge"],
    queryFn: () => api<Knowledge[]>(ROOT + "/knowledge"),
  });
  const save = useMutation({
    mutationFn: (data: Knowledge) =>
      api(ROOT + "/knowledge" + (editing ? "/" + editing.id : ""), {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify(
          editing
            ? { expected_revision: editing.revision, payload: data }
            : data,
        ),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["configuration"] });
      setEditing(undefined);
    },
    onError: (e) => message.error(e.message),
  });
  const bulkSave = useMutation({
    mutationFn: (items: unknown[]) =>
      api(ROOT + "/knowledge/batch", {
        method: "POST",
        body: JSON.stringify({ items }),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["configuration"] });
      setBatchOpen(false);
      setSelected([]);
    },
    onError: (e) => message.error(e.message),
  });
  return (
    <div className="configuration-page">
      <Typography.Title level={2}>搭配知识</Typography.Title>
      <Alert
        type="info"
        showIcon
        title="维护通用条件与明确例外，保留每条关系的依据。"
        description="只有已确认知识参与检查；资料缺失和知识冲突分别展示，推荐关系不抵消不兼容条件。"
      />
      {query.error ? <Alert type="error" title={query.error.message} /> : null}
      <Space wrap>
        <Input.Search
          placeholder="查找搭配、系统或角色"
          onChange={(e) => setSearch(e.target.value)}
        />
        <Button type="primary" onClick={() => setEditing(null)}>
          新增搭配知识
        </Button>
        <Button disabled={!selected.length} onClick={() => setBatchOpen(true)}>
          批量编辑
        </Button>
      </Space>
      <Table<Knowledge>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data?.filter((k) =>
          `${k.name} ${k.system} ${k.role}`.includes(search),
        )}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as string[]),
        }}
        scroll={{ x: 1050 }}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "类型", render: (_, k) => kinds[k.kind] },
          { title: "系统 / 角色", render: (_, k) => k.system + " / " + k.role },
          {
            title: "结论",
            render: (_, k) => (k.effect === "deny" ? "不兼容" : "条件满足可用"),
          },
          { title: "状态", render: (_, k) => <Status value={k.status} /> },
          { title: "版本", dataIndex: "revision" },
          { title: "依据", dataIndex: "evidence" },
          {
            title: "操作",
            render: (_, k) => (
              <Space>
                <Button onClick={() => setEditing(k)}>编辑</Button>
                <Button onClick={() => setHistory(k.id)}>历史</Button>
              </Space>
            ),
          },
        ]}
      />
      {batchOpen ? (
        <KnowledgeBatch
          selected={query.data?.filter((k) => selected.includes(k.id)) ?? []}
          onSave={(items) => bulkSave.mutate(items)}
          onClose={() => setBatchOpen(false)}
          busy={bulkSave.isPending}
        />
      ) : null}
      <Modal
        title="搭配知识修订记录"
        open={!!history}
        onCancel={() => setHistory(undefined)}
        footer={null}
      >
        <Table
          rowKey="revision"
          dataSource={revisions.data}
          columns={[
            { title: "版本", dataIndex: "revision" },
            { title: "维护人", dataIndex: "actor" },
            { title: "依据", dataIndex: "evidence" },
          ]}
        />
      </Modal>
      {editing !== undefined ? (
        <KnowledgeEditor
          initial={editing ?? undefined}
          onSave={(v) => save.mutate(v)}
          onClose={() => setEditing(undefined)}
          busy={save.isPending}
        />
      ) : null}
    </div>
  );
}
