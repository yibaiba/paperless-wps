import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Card, Form, Input, InputNumber, Modal, Select, Space, Table, Typography } from "antd";
import { api } from "../../../shared/api";
import { AuthorFields, required, ROOT, Status, units, useAttributeDefinitions } from "../shared";
import { definitionsKey } from "./useDefinitions";
import type { InspectionProfile } from "./inspectionTypes";
export const inspectionKey = ["configuration", "inspection-profiles"] as const;

export function InspectionProfiles() {
  const [params] = useSearchParams();
  const query = useQuery({ queryKey: inspectionKey, queryFn: () => api<InspectionProfile[]>(ROOT + "/inspection-profiles") });
  const [editing, setEditing] = useState<InspectionProfile | null>();
  const { message } = App.useApp(); const client = useQueryClient();
  const save = useMutation({
    mutationFn: (value: unknown) => api(ROOT + "/inspection-profiles" + (editing ? "/" + editing.id : ""), {
      method: editing ? "PUT" : "POST", body: JSON.stringify(editing ? { expected_revision: editing.revision, payload: value } : value),
    }),
    onSuccess: () => { client.invalidateQueries({ queryKey: inspectionKey }); client.invalidateQueries({ queryKey: definitionsKey }); setEditing(undefined); message.success("用途检查已保存；系统角色仍使用其选定修订"); },
    onError: (error) => message.error(error.message),
  });
  const selected = params.get("profile");
  return <Card title="可复用用途检查" extra={<Button type="primary" onClick={() => setEditing(null)}>新增用途检查</Button>}>
    <Typography.Paragraph type="secondary">维护一次，由系统角色引用固定修订。产品适配仍按搭配知识检查；更新不会改写已有项目。</Typography.Paragraph>
    {query.error ? <Alert type="error" title={query.error.message} /> : null}
    <Table<InspectionProfile> rowKey="id" loading={query.isLoading} dataSource={query.data?.filter((p) => !selected || p.id === selected)} columns={[
      { title: "用途", dataIndex: "name" }, { title: "指标", render: (_, p) => p.metrics.map((m) => m.label).join("、") || "尚未定义" },
      { title: "状态", render: (_, p) => <Status value={p.status} /> }, { title: "修订", dataIndex: "revision" },
      { title: "操作", render: (_, p) => <Button onClick={() => setEditing(p)}>维护检查</Button> },
    ]} />
    {editing !== undefined ? <InspectionEditor initial={editing ?? undefined} busy={save.isPending} onClose={() => setEditing(undefined)} onSave={(v) => save.mutate(v)} /> : null}
  </Card>;
}

function InspectionEditor({ initial, busy, onClose, onSave }: { initial?: InspectionProfile; busy: boolean; onClose: () => void; onSave: (value: unknown) => void }) {
  const [form] = Form.useForm(); const definitions = useAttributeDefinitions();
  return <Modal open width={980} title="用途检查定义" confirmLoading={busy} onCancel={onClose} onOk={() => form.submit()}>
    <Form form={form} layout="vertical" initialValues={initial ?? { status: "draft", selected_device_policy: "unknown", metrics: [] }} onFinish={onSave}>
      <Form.Item name="name" label="用途名称" rules={required}><Input placeholder="例如：会议服务端的终端承载检查" /></Form.Item>
      <Space wrap align="start">
        <Form.Item name="status" label="依据确认状态"><Select style={{ width: 180 }} options={[{ value: "draft", label: "草稿待核对" }, { value: "confirmed", label: "已有依据，可执行" }, { value: "disabled", label: "停用" }]} /></Form.Item>
        <Form.Item name="selected_device_policy" label="角色直接选择的产品"><Select style={{ width: 240 }} options={[{ value: "unknown", label: "尚未确认检查范围" }, { value: "required", label: "需要检查容量" }, { value: "not_applicable", label: "不涉及容量（仍检查适配与配套）" }]} /></Form.Item>
      </Space>
      <Form.List name="metrics">{(fields, { add, remove }) => <Space orientation="vertical" style={{ width: "100%" }}>
        {fields.map((field) => <Card size="small" key={field.key} title={`检查指标 ${field.name + 1}`} extra={<Button onClick={() => remove(field.name)}>移除指标</Button>}>
          <Space wrap align="start">
            <Form.Item name={[field.name, "label"]} label="检查名称" rules={required}><Input placeholder="终端承载量" /></Form.Item>
            <Form.Item name={[field.name, "key"]} label="产品容量字段" rules={required}><Select showSearch optionFilterProp="label" style={{ width: 200 }} options={definitions.data?.filter((d) => ["number", "quantity"].includes(d.kind)).map((d) => ({ value: d.key, label: `${d.label} · ${d.key}` }))} /></Form.Item>
            <Form.Item name={[field.name, "input_label"]} label="售前填写项名称" rules={required}><Input placeholder="本系统终端数量" /></Form.Item>
            <Form.Item name={[field.name, "input_key"]} label="项目输入标识" rules={required}><Input placeholder="terminal_count" /></Form.Item>
            <Form.Item name={[field.name, "unit"]} label="产品容量单位" rules={required}><Select style={{ width: 120 }} options={units.map((u) => ({ value: u, label: u }))} /></Form.Item>
            <Form.Item name={[field.name, "input_unit"]} label="项目输入单位" rules={required}><Select style={{ width: 120 }} options={units.map((u) => ({ value: u, label: u }))} /></Form.Item>
            <Form.Item name={[field.name, "factor"]} label="每单位资源需求" rules={required}><InputNumber stringMode min="0" /></Form.Item>
            <Form.Item name={[field.name, "aggregation"]} label="共用时需求如何合计"><Select style={{ width: 180 }} options={[{ value: "sum", label: "各用途需求相加" }, { value: "max", label: "按最大需求（须有依据）" }]} /></Form.Item>
            <Form.Item name={[field.name, "capacity_basis"]} label="产品容量口径"><Select style={{ width: 190 }} options={[{ value: "deployment", label: "本部署的整体容量" }, { value: "unit", label: "单台容量 × 部署数量" }]} /></Form.Item>
            <Form.Item name={[field.name, "applies_to"]} label="资源由谁承担"><Select style={{ width: 160 }} options={[{ value: "selected_device", label: "当前选中设备" }, { value: "accessory", label: "指定配套设备" }]} onChange={(v) => { if (v === "selected_device") form.setFieldValue(["metrics", field.name, "target_need_key"], ""); }} /></Form.Item>
            <Form.Item noStyle shouldUpdate>{() => form.getFieldValue(["metrics", field.name, "applies_to"]) === "accessory" ? <Form.Item name={[field.name, "target_need_key"]} label="配套需求标识" rules={required}><Input placeholder="server" /></Form.Item> : <Form.Item name={[field.name, "target_need_key"]} hidden><Input /></Form.Item>}</Form.Item>
          </Space>
        </Card>)}
        <Button onClick={() => add({ key: "", label: "", input_key: "", input_label: "", input_unit: "", unit: "", factor: "1", aggregation: "sum", capacity_basis: "deployment", applies_to: "selected_device", target_need_key: "" })}>增加检查指标</Button>
      </Space>}</Form.List>
      <AuthorFields />
    </Form>
  </Modal>;
}
