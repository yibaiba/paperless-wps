import { RecommendationFields } from "./RecommendationFields";
import { useState } from "react";
import { PackageChangePreview } from "./PackageChangePreview";
import { Alert, Button, Checkbox, Form, Input, Modal, Select, Space, Typography } from "antd";
import type { KnowledgePackage } from "../types";
import { AuthorFields, required, useKnowledge, useVariants, variantOptions } from "../shared";
import { useDefinitions } from "./useDefinitions";

export function KnowledgePackageEditor({ initial, busy, onSave, onClose }: {
  initial?: KnowledgePackage; busy: boolean; onSave: (value: unknown) => void; onClose: () => void;
}) {
  const [form] = Form.useForm();
  const [preview, setPreview] = useState<unknown>();
  const useLatest = Form.useWatch("use_latest", form);
  const upgrades = Form.useWatch("upgrade_member_ids", form) as string[] | undefined;
  const definitions = useDefinitions(), knowledge = useKnowledge(), variants = useVariants();
  const definitionId = Form.useWatch("system_definition_id", form);
  const definition = !useLatest && initial && initial.system_definition_id === definitionId ? initial.definition : definitions.data?.definitions.find((d) => d.id === definitionId);
  const submit = (values: Record<string, unknown>) => {
    const { member_ids, use_latest, upgrade_member_ids, ...fields } = values;
    const members = (member_ids as string[]).map((id) => ({ id,
      revision: !(upgrade_member_ids as string[] | undefined)?.includes(id) && initial?.members.find((m) => m.id === id)?.revision || knowledge.data!.find((k) => k.id === id)!.revision,
    }));
    const payload = { ...fields, members,
      definition_revision: !use_latest && initial && initial.system_definition_id === definitionId ? initial.definition_revision : definition!.revision,
    };
    if (initial) setPreview(payload); else onSave(payload);
  };
  return <><Modal open title="系统知识包与资料覆盖" okText={initial ? "预览本次变更" : "保存草稿"} width={1000} onCancel={onClose} onOk={() => form.submit()} confirmLoading={busy} okButtonProps={{ disabled: definitions.isPending || knowledge.isPending || !!definitions.error || !!knowledge.error }}>
    {definitions.error || knowledge.error ? <Alert type="error" title={definitions.error?.message ?? knowledge.error?.message} /> : null}
    <Form form={form} layout="vertical" initialValues={initial ? {
      name: initial.name, branch: initial.branch, status: initial.status,
      system_definition_id: initial.system_definition_id, member_ids: initial.members.map((m) => m.id),
      recommendations: initial.recommendations ?? [], coverage: initial.coverage, actor: initial.actor, evidence: initial.evidence,
    } : { status: "draft", member_ids: [], coverage: [], recommendations: [] }} onFinish={() => submit(form.getFieldsValue(true))}>
      <Space wrap align="start">
        <Form.Item name="name" label="知识包名称" rules={required}><Input /></Form.Item>
        <Form.Item name="system_definition_id" label="系统版本" rules={required}><Select style={{ width: 280 }} options={definitions.data?.definitions.map((d) => ({ value: d.id, label: d.name }))} /></Form.Item>
        <Form.Item name="branch" label="环境分支名称" rules={required}><Input placeholder="例如 Windows；具体条件写在成员关系中" /></Form.Item>
      </Space>
      <Form.Item name="member_ids" label="引用的知识关系"><Select mode="multiple" showSearch optionFilterProp="label" options={knowledge.data?.map((k) => { const chosen = !upgrades?.includes(k.id) ? initial?.rules.find(r => r.id === k.id) ?? k : k; return { value: k.id, label: `${chosen.name} · v${chosen.revision} · ${chosen.status}` }; })} /></Form.Item>
      {definition ? <Typography.Paragraph type="secondary">正在编辑角色定义 v{definition.revision} 的覆盖结论。</Typography.Paragraph> : null}
      {initial ? <Form.Item name="use_latest" valuePropName="checked"><Checkbox>明确升级系统角色定义到最新修订</Checkbox></Form.Item> : null}
      {initial ? <Form.Item name="upgrade_member_ids" label="逐项选择采用最新修订的关系"><Select mode="multiple" options={initial.members.flatMap(m => { const current = knowledge.data?.find(k => k.id === m.id); return current && current.revision !== m.revision ? [{ value: m.id, label: `${current.name} · v${m.revision} → v${current.revision}` }] : []; })} /></Form.Item> : null}
      <Form.List name="coverage">{(fields, { add, remove }) => <Space orientation="vertical" style={{ width: "100%" }}>
        {fields.map((field) => <div key={field.key}>
          <Space wrap align="start">
            <Form.Item name={[field.name, "role_id"]} label="核对角色" rules={required}><Select style={{ width: 170 }} options={definition?.roles.map((r) => ({ value: r.id, label: r.name }))} /></Form.Item>
            <Form.Item name={[field.name, "accessories"]} label="配套范围核对结论"><Select style={{ width: 200 }} options={[
              { value: "unreviewed", label: "尚未核对" }, { value: "needs_review", label: "仍有待确认项" },
              { value: "complete", label: "已完整列出所需配套" }, { value: "none", label: "明确无需额外配套" },
            ]} /></Form.Item>
            <Form.Item name={[field.name, "resources"]} label="本角色选中配置的资源核算"><Select style={{ width: 200 }} options={[
              { value: "unknown", label: "待确认" }, { value: "required", label: "需要核算" }, { value: "not_applicable", label: "明确不涉及资源容量" },
            ]} /></Form.Item>
            <Button onClick={() => remove(field.name)}>移除核对项</Button>
          </Space>
          <Form.Item name={[field.name, "selector", "variant_ids"]} label="结论覆盖的配置" rules={required}><Select mode="multiple" showSearch optionFilterProp="label" options={variantOptions(variants.data)} /></Form.Item>
          <Form.Item name={[field.name, "evidence"]} label="核对依据" rules={required}><Input.TextArea /></Form.Item>
        </div>)}
        <Button disabled={!definition} onClick={() => add({ role_id: "", selector: { variant_ids: [], category: "", series: [], exclude_variant_ids: [] }, accessories: "unreviewed", resources: "unknown", evidence: "" })}>增加产品范围核对</Button>
      </Space>}</Form.List>
      <RecommendationFields definition={definition} />
      <Form.Item name="status" label="发布状态"><Select options={[{ value: "draft", label: "草稿" }, { value: "published", label: "发布固定修订，供项目明确选择" }]} /></Form.Item>
      <AuthorFields />
    </Form>
  </Modal>{initial && preview ? <PackageChangePreview original={initial} payload={preview} busy={busy} onClose={() => setPreview(undefined)} onApply={() => onSave(preview)} /> : null}</>;
}
