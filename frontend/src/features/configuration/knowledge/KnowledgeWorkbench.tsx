import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Card, Collapse, Empty, Select, Space, Table, Tag, Typography } from "antd";
import { api } from "../../../shared/api";
import { ROOT, Status, useKnowledge, useVariants, variantOptions } from "../shared";
import type { Knowledge, Variant } from "../types";
import { emptyKnowledge, KnowledgeEditor, normalizeKnowledge } from "../KnowledgeEditor";
import { KnowledgeQuickCreate } from "../KnowledgeQuickCreate";
import { VariantEditor } from "../CatalogEditor";
import { copyKnowledge, requiresAdvanced } from "./quickEdit";
import { configurationKeys } from "../queryKeys";
import { useDefinitions } from "./useDefinitions";

const relationNames = { suitability: "系统适用", accessory: "配套需求", sharing: "共用条件" };

export function KnowledgeWorkbench() {
  const [params] = useSearchParams();
  const variants = useVariants(), knowledge = useKnowledge(), definitions = useDefinitions();
  const [selected, setSelected] = useState<string[]>(params.get("variant") ? [params.get("variant")!] : []);
  const [focusedRule, setFocusedRule] = useState(params.get("rule"));
  const [system, setSystem] = useState<string>();
  const [roleId, setRoleId] = useState<string>();
  const [variantEditing, setVariantEditing] = useState<Variant>();
  const [advanced, setAdvanced] = useState(false);
  const [editing, setEditing] = useState<{ original?: Knowledge; value: Knowledge }>();
  const { message } = App.useApp(), client = useQueryClient();
  const save = useMutation({
    mutationFn: (value: Knowledge) => api(ROOT + "/knowledge" + (editing?.original ? "/" + editing.original.id : ""), {
      method: editing?.original ? "PUT" : "POST",
      body: JSON.stringify(editing?.original ? { expected_revision: editing.original.revision, payload: normalizeKnowledge(value) } : normalizeKnowledge(value)),
    }),
    onSuccess: () => { client.invalidateQueries({ queryKey: configurationKeys.knowledge }); setEditing(undefined); message.success("搭配知识已保存"); },
    onError: (e) => message.error(e.message),
  });
  const chosen = variants.data?.filter((v) => selected.includes(v.id)) ?? [];
  const rules = knowledge.data?.filter((k) => (!focusedRule || k.id === focusedRule) && (!selected.length || chosen.some((v) => matches(v, k))) &&
    (!system || k.system_definition_id === system || k.system === definitions.data?.definitions.find((d) => d.id === system)?.name || k.shared_role_refs?.some(r => r.system_definition_id === system) || (k.kind === "accessory" && !k.system_definition_id && !k.system)) && (!roleId || !k.role_id || k.role_id === roleId));
  const add = (kind: Knowledge["kind"]) => { setAdvanced(false); setEditing({ value: {
    ...emptyKnowledge, kind, system_definition_id: system ?? "",
    system: definitions.data?.definitions.find((d) => d.id === system)?.name ?? "",
    role_id: roleId ?? "", role: definitions.data?.definitions.find(d => d.id === system)?.roles.find(r => r.id === roleId)?.name ?? "",
    selector: { ...emptyKnowledge.selector, variant_ids: selected },
  } as unknown as Knowledge }); };
  return <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
    <Alert type="info" showIcon title="先选产品，再集中维护搭配" description="可多选配置，共性关系只保存一条。原资料就在旁边，数量和共用依据不足时保留待确认。" />
    {focusedRule ? <Alert type="info" title="已定位项目待确认事项对应的知识" action={<Button onClick={() => setFocusedRule(null)}>查看全部关系</Button>} /> : null}
    {(variants.error || knowledge.error || definitions.error) ? <Alert type="error" title={(variants.error || knowledge.error || definitions.error)?.message} /> : null}
    <div className="knowledge-workbench">
      <Card title="产品范围与原始资料">
        <Space orientation="vertical" style={{ width: "100%" }} size="middle">
          <Select aria-label="选择产品配置范围" mode="multiple" showSearch optionFilterProp="label" placeholder="多选要一起维护的配置"
            value={selected} onChange={setSelected} options={variantOptions(variants.data)} style={{ width: "100%" }} />
          <Select aria-label="知识系统版本筛选" allowClear placeholder="全部系统版本" value={system} onChange={value => { setSystem(value); setRoleId(undefined); }}
            options={definitions.data?.definitions.map((d) => ({ value: d.id, label: d.name }))} style={{ width: "100%" }} />
          {system ? <Select aria-label="承担角色筛选" allowClear placeholder="全部角色及通用配套" value={roleId} onChange={setRoleId} options={definitions.data?.definitions.find(d => d.id === system)?.roles.map(r => ({ value: r.id, label: r.name }))} style={{ width: '100%' }} /> : null}
          {!chosen.length ? <Empty description="选择产品查看规格和资料依据" /> : <Collapse items={chosen.map((v) => ({
            key: v.id, label: `${v.product.model} · ${v.name}`, children: <Space orientation="vertical">
              <Button onClick={() => setVariantEditing(v)}>维护基本配置与已包含内容</Button>
              <Typography.Text>参数：{v.attributes.map(a => `${a.key}：${a.value ?? "未知"} ${a.unit}`).join("；") || "尚未登记"}</Typography.Text>
              {v.source_details?.map((source) => <div key={source.id}>
                <Typography.Text strong>{source.sheet} · 第 {source.row} 行</Typography.Text>
                <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>{source.specification}</Typography.Paragraph>
                {source.note ? <Typography.Paragraph type="secondary">{source.note}</Typography.Paragraph> : null}
              </div>)}
            </Space>,
          }))} />}
        </Space>
      </Card>
      <Card title="适用、配套与共享" extra={<Typography.Text type="secondary">{rules?.length ?? 0} 条关系</Typography.Text>}>
        <Space wrap style={{ marginBottom: 16 }}>
          {Object.entries(relationNames).map(([kind, name]) => <Button key={kind} disabled={!selected.length} onClick={() => add(kind as Knowledge["kind"])}>添加{name}</Button>)}
        </Space>
        <Table<Knowledge> rowKey="id" dataSource={rules} loading={knowledge.isLoading} scroll={{ x: 720 }} columns={[
          { title: "关系", render: (_, k) => <><Typography.Text strong>{k.name}</Typography.Text><div><Tag>{relationNames[k.kind]}</Tag>{k.system} {k.role}</div></> },
          { title: "数量与依据", render: (_, k) => k.kind !== "accessory" ? "查看适用条件" : <><div>{k.target_variant_ids.length ? `候选 ${k.target_variant_ids.length} 个` : '候选型号待补'}</div>{quantityLabel(k)}<div>数量依据：<Status value={k.quantity_review === "confirmed" ? "confirmed" : "unknown"} /></div><div>容量：{({ unknown: '待确认', required: '需核算', not_applicable: '明确不涉及' })[k.resource_policy ?? "unknown"]}</div></> },
          { title: "状态", width: 90, render: (_, k) => <Status value={k.status} /> },
          { title: "操作", width: 150, render: (_, k) => <Space>
            <Button size="small" onClick={() => { setAdvanced(requiresAdvanced(k)); setEditing({ original: k, value: k }); }}>维护</Button>
            <Button size="small" onClick={() => { setAdvanced(requiresAdvanced(k)); setEditing({ value: copyKnowledge(k) }); }}>复制草稿</Button>
          </Space> },
        ]} />
      </Card>
    </div>
    {variantEditing ? <VariantEditor variant={variantEditing} onClose={() => setVariantEditing(undefined)} /> : null}
    {editing ? advanced ? <KnowledgeEditor key={editing.original?.id ?? "new"} initial={editing.value} busy={save.isPending} onClose={() => setEditing(undefined)} onSave={v => save.mutate(v)} /> : <KnowledgeQuickCreate key={editing.original?.id ?? "new"} initial={editing.value} busy={save.isPending} onClose={() => setEditing(undefined)} onSave={v => save.mutate(v)} onAdvanced={value => { setEditing({ ...editing, value }); setAdvanced(true); }} /> : null}
  </Space>;
}

function matches(variant: Variant, knowledge: Knowledge) {
  const s = knowledge.selector;
  return !s.exclude_variant_ids.includes(variant.id) &&
    (!s.variant_ids.length || s.variant_ids.includes(variant.id)) &&
    (!s.category || s.category === variant.product.category) &&
    (!s.series.length || s.series.some((series) => variant.series.includes(series)));
}

function quantityLabel(knowledge: Knowledge) {
  if (!knowledge.factor || !knowledge.mode || !knowledge.calculation_scope) return "数量待确认";
  const scope = { device: "每个设备", system: "每个系统", room: "每个房间", project: "整个项目" }[knowledge.calculation_scope];
  const formula = {
    per_unit: `数量 × ${knowledge.factor}`,
    per_capacity: `数量 ÷ ${knowledge.factor}，向上取整`,
    per_group: `固定 ${knowledge.factor}`,
  }[knowledge.mode];
  return `${scope}：${formula}`;
}
