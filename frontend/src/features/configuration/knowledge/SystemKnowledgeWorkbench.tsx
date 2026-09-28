import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Card, Form, Input, Modal, Space, Table, Tag } from "antd";
import { api } from "../../../shared/api";
import { ROOT, AuthorFields, required } from "../shared";
import type { KnowledgePackage, SystemDefinition } from "../types";
import { definitionsKey, packagesKey, useDefinitions } from "./useDefinitions";
import { SystemDefinitionEditor } from "./SystemDefinitionEditor";
import { KnowledgePackageEditor } from "./KnowledgePackageEditor";

import { DefinitionMapping } from "./DefinitionMapping";

export function SystemKnowledgeWorkbench() {
  const definitions = useDefinitions();
  const packages = useQuery({ queryKey: packagesKey, queryFn: () => api<KnowledgePackage[]>(ROOT + "/knowledge-packages") });
  const [definition, setDefinition] = useState<SystemDefinition | null>();
  const [bundle, setBundle] = useState<KnowledgePackage | null>();
  const [capability, setCapability] = useState(false);
  const { message } = App.useApp(), client = useQueryClient();
  const save = useMutation({
    mutationFn: ({ path, original, value }: { path: string; original?: { id: string; revision: number } | null; value: unknown }) => api(ROOT + path + (original ? "/" + original.id : ""), {
      method: original ? "PUT" : "POST", body: JSON.stringify(original ? { expected_revision: original.revision, payload: value } : value),
    }),
    onSuccess: () => { client.invalidateQueries({ queryKey: definitionsKey }); client.invalidateQueries({ queryKey: packagesKey }); setDefinition(undefined); setBundle(undefined); setCapability(false); message.success("已保存修订，现有项目不会自动更新"); },
    onError: (e) => message.error(e.message),
  });
  return <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
    <Alert showIcon type="info" title="角色定义与搭配知识分别维护" description="角色定义说明需要什么；知识包引用已选关系的固定修订。发布知识包不代表所有搭配已确认，缺少依据的部分继续显示待办。" />
    {definitions.error || packages.error ? <Alert type="error" title={(definitions.error || packages.error)?.message} /> : null}
    <DefinitionMapping />
    <Card title="系统版本与角色" extra={<Space><Button onClick={() => setCapability(true)}>增加能力定义</Button><Button type="primary" onClick={() => setDefinition(null)}>新增系统定义</Button></Space>}>
      <Table<SystemDefinition> rowKey="id" dataSource={definitions.data?.definitions} columns={[
        { title: "系统版本", dataIndex: "name" }, { title: "角色", render: (_, d) => d.roles.map((r) => <Tag key={r.id}>{r.name}{r.required ? " · 必要" : ""}{r.feature ? ` · 功能 ${r.feature}` : ""}</Tag>) },
        { title: "状态", dataIndex: "status" }, { title: "修订", dataIndex: "revision" },
        { title: "操作", render: (_, d) => <Button onClick={() => setDefinition(d)}>维护角色</Button> },
      ]} />
    </Card>
    <Card title="按系统与环境发布知识包" extra={<Button type="primary" onClick={() => setBundle(null)}>新增知识包</Button>}>
      <Table<KnowledgePackage> rowKey="id" dataSource={packages.data} columns={[
        { title: "名称", dataIndex: "name" }, { title: "环境分支", dataIndex: "branch" },
        { title: "引用关系", render: (_, p) => `${p.members.length} 条固定修订` }, { title: "核对范围", render: (_, p) => `${p.coverage.length} 项` },
        { title: "状态", dataIndex: "status" }, { title: "修订", dataIndex: "revision" },
        { title: "操作", render: (_, p) => <Button onClick={() => setBundle(p)}>维护知识包</Button> },
      ]} />
    </Card>
    {definition !== undefined ? <SystemDefinitionEditor initial={definition ?? undefined} busy={save.isPending} onClose={() => setDefinition(undefined)} onSave={(value) => save.mutate({ path: "/definitions", original: definition, value })} /> : null}
    {bundle !== undefined ? <KnowledgePackageEditor initial={bundle ?? undefined} busy={save.isPending} onClose={() => setBundle(undefined)} onSave={(value) => save.mutate({ path: "/knowledge-packages", original: bundle, value })} /> : null}
    <Modal open={capability} title="能力定义" onCancel={() => setCapability(false)} footer={null} destroyOnHidden>
      <Form layout="vertical" onFinish={(value) => save.mutate({ path: "/capabilities", value })}>
        <Form.Item name="name" label="能力名称" rules={required}><Input /></Form.Item>
        <Form.Item name="description" label="能力说明" initialValue=""><Input.TextArea /></Form.Item>
        <AuthorFields /><Button htmlType="submit" type="primary" loading={save.isPending}>保存能力</Button>
      </Form>
    </Modal>
  </Space>;
}
