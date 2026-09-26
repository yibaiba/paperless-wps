import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Typography,
} from "antd";
import { api } from "../../shared/api";
import type { Knowledge } from "./types";
import { ROOT, Status, useKnowledge } from "./shared";
import { KnowledgeEditor } from "./KnowledgeEditor";
import "./configuration.css";
import { KnowledgeBatch } from "./KnowledgeBatch";
import { KnowledgeTrial } from "./KnowledgeTrial";
import { KnowledgeMigration } from "./KnowledgeMigration";
const kinds = {
  suitability: "系统适用",
  accessory: "配套关系",
  sharing: "共用部署",
};
export default function KnowledgePage() {
  const [batchOpen, setBatchOpen] = useState(false),
    [history, setHistory] = useState<string>(),
    [systemFilter, setSystemFilter] = useState<string>(),
    [evidence, setEvidence] = useState<string>(),
    [trial, setTrial] = useState<Knowledge>(),
    [help, setHelp] = useState(false);
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
  const query = useKnowledge();
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
        title="按具体系统版本维护搭配，运行环境单独检查。"
        description="红盾、充电柜传输版、华为版本、分布式2.0、安全V3.0分别维护；Windows、麒麟、统信是运行环境。相同型号出现在不同版本中，不代表软件互通或可以共用部署。只有已确认知识参与检查。"
      />
      {query.error ? <Alert type="error" title={query.error.message} /> : null}
      <Space wrap>
        <Button onClick={() => setHelp(true)}>系统如何使用这些知识</Button>
        <Select
          aria-label="筛选系统版本"
          allowClear
          showSearch
          value={systemFilter}
          onChange={setSystemFilter}
          placeholder="全部系统 / 方案版本"
          style={{ width: 290 }}
          options={[
            ...new Set(query.data?.map((k) => k.system).filter(Boolean) ?? []),
          ]
            .sort()
            .map((value) => ({ value, label: value }))}
        />
        <Input.Search
          placeholder="查找搭配、系统或角色"
          onChange={(e) => setSearch(e.target.value)}
        />
        <Button type="primary" onClick={() => setEditing(null)}>
          新增搭配知识
        </Button>
        <KnowledgeMigration />
        <Button disabled={!selected.length} onClick={() => setBatchOpen(true)}>
          批量编辑
        </Button>
      </Space>
      <Table<Knowledge>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data?.filter(
          (k) =>
            (!systemFilter || k.system === systemFilter) &&
            `${k.name} ${k.system} ${k.role}`.includes(search),
        )}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as string[]),
        }}
        scroll={{ x: 1690 }}
        tableLayout="fixed"
        className="knowledge-table"
        columns={[
          { title: "名称", dataIndex: "name", width: 280 },
          { title: "类型", render: (_, k) => kinds[k.kind], width: 110 },
          {
            title: "系统 / 方案版本",
            render: (_, k) => k.system || "按产品配置限定",
            width: 240,
          },
          { title: "承担角色", render: (_, k) => k.role || "—", width: 120 },
          {
            title: "结论",
            width: 130,
            render: (_, k) => {
              if (k.status === "draft") return "待确认";
              if (k.status === "disabled") return "不参与检查";
              return k.effect === "deny" ? "不兼容" : "条件满足可用";
            },
          },
          {
            title: "完整程度",
            width: 140,
            render: (_, k) =>
              k.kind === "accessory" && k.completion === "incomplete" ? (
                <Typography.Text type="warning">
                  待补：{k.missing_fields?.join("、")}
                </Typography.Text>
              ) : (
                "完整"
              ),
          },
          {
            title: "状态",
            render: (_, k) => <Status value={k.status} />,
            width: 100,
          },
          { title: "修订", dataIndex: "revision", width: 70 },
          {
            title: "依据",
            width: 350,
            render: (_, k) => (
              <>
                <Typography.Paragraph
                  ellipsis={{ rows: 2 }}
                  style={{ marginBottom: 4 }}
                >
                  {k.evidence}
                </Typography.Paragraph>
                <Button
                  type="link"
                  size="small"
                  onClick={() => setEvidence(k.evidence)}
                >
                  查看完整依据
                </Button>
              </>
            ),
          },
          {
            title: "操作",
            width: 230,
            render: (_, k) => (
              <Space>
                <Button onClick={() => setEditing(k)}>编辑</Button>
                <Button onClick={() => setHistory(k.id)}>历史</Button>
                {k.kind === "suitability" ? (
                  <Button onClick={() => setTrial(k)}>试算</Button>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
      {trial ? (
        <KnowledgeTrial
          key={trial.id}
          knowledge={trial}
          onClose={() => setTrial(undefined)}
        />
      ) : null}
      <Modal
        title="从知识到项目清单"
        open={help}
        onCancel={() => setHelp(false)}
        footer={null}
      >
        <Typography.Paragraph>
          1. 在项目清单中创建或打开项目，进入“需求选配与拓扑”。
        </Typography.Paragraph>
        <Typography.Paragraph>
          2.
          添加房间和具体系统版本，再添加服务端、客户端等角色需求，填写运行环境、规模与资源需求。
        </Typography.Paragraph>
        <Typography.Paragraph>
          3.
          选中角色查看候选。系统按已确认知识检查产品，展开“依据”查看通过、冲突或资料不足的原因。只有你选择的配置才进入清单。
        </Typography.Paragraph>
        <Typography.Paragraph>
          4.
          点击“检查当前配置”，查看容量、共用部署和配套建议。配件由你选择后补入；草稿、未知数量和缺少型号依据的要求不会自动加料。
        </Typography.Paragraph>
        <Typography.Paragraph>
          5.
          保存项目版本。知识更新后使用“按最新资料重新检查”；旧项目不会被后台规则改写。
        </Typography.Paragraph>
        <Button type="primary" href="/projects">
          前往项目清单
        </Button>
      </Modal>
      <Modal
        title="搭配依据"
        open={!!evidence}
        onCancel={() => setEvidence(undefined)}
        footer={null}
      >
        <div className="config-source">{evidence}</div>
      </Modal>
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
