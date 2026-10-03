import { useState } from "react";
import { Alert, Button, Form, Input, Modal, Select, Space, Steps, Typography } from "antd";
import type { Knowledge } from "./types";
import { emptyKnowledge, normalizeKnowledge } from "./KnowledgeEditor";
import { AuthorFields, useVariants } from "./shared";
import { KnowledgeRelationStep } from "./knowledge/KnowledgeRelationStep";
import { KnowledgeRuleStep } from "./knowledge/KnowledgeRuleStep";
import { KnowledgeSentence } from "./knowledge/KnowledgeSentence";
import { mergeQuickEdit, matchingConfigurations } from "./knowledge/quickEdit";
import { SourceEvidencePanel } from "./knowledge/SourceEvidencePanel";
import { EvidenceReferenceFields } from "./knowledge/EvidenceReferenceFields";
import { knowledgeName, knowledgeSummary } from "./knowledge/knowledgeQuickSummary";

const stepItems = [
  { title: "选择关系", content: "产品和业务含义" },
  { title: "确认规则", content: "数量与限制条件" },
  { title: "依据与保存", content: "维护人和确认状态" },
];

export function KnowledgeQuickCreate({
  onSave,
  onClose,
  busy,
  initial,
  onAdvanced,
}: {
  initial?: Partial<Knowledge>;
  onAdvanced?: (value: Knowledge) => void;
  onSave: (values: Knowledge) => void;
  onClose: () => void;
  busy: boolean;
}) {
  const [form] = Form.useForm();
  const [step, setStep] = useState(0);
  const variants = useVariants();
  const kind = Form.useWatch("kind", form) as Knowledge["kind"] | undefined;
  const quantitySource = Form.useWatch("quantity_source", form) as
    | Knowledge["quantity_source"]
    | undefined;
  const values = Form.useWatch([], form) as Knowledge | undefined;
  const summary = knowledgeSummary(values, variants.data);
  const next = async () => {
    await form.validateFields(firstStepFields(kind));
    setStep((current) => Math.min(current + 1, stepItems.length - 1));
  };
  return (
    <Modal
      open
      width={1250}
      title={initial?.id ? "维护产品搭配" : "新增产品搭配"}
      onCancel={onClose}
      footer={
        <Space>
          {onAdvanced ? <Button onClick={() => onAdvanced(mergeQuickEdit({ ...emptyKnowledge, ...initial } as Knowledge, form.getFieldsValue(true)))}>高级编辑</Button> : null}
          <Button onClick={step ? () => setStep(step - 1) : onClose}>
            {step ? "上一步" : "取消"}
          </Button>
          {step < stepItems.length - 1 ? (
            <Button type="primary" onClick={next}>下一步</Button>
          ) : (
            <Button type="primary" loading={busy} onClick={() => form.submit()}>
              保存知识
            </Button>
          )}
        </Space>
      }
    >
      <Steps current={step} items={stepItems} style={{ marginBottom: 24 }} />
      <Form
        form={form}
        layout="vertical"
        initialValues={{ ...emptyKnowledge, ...initial }}
        onFinishFailed={({ errorFields }) =>
          setStep(errorStep(errorFields.map((item) => item.name)))
        }
        onFinish={(submitted) =>
          onSave(
            normalizeKnowledge({
              ...mergeQuickEdit({ ...emptyKnowledge, ...initial } as Knowledge, submitted),
              name:
                submitted.name?.trim() ||
                knowledgeName(submitted, variants.data),
            }),
          )
        }
      >
        <div className="knowledge-workbench knowledge-form-workbench"><div>
        <section hidden={step !== 0}>
          <KnowledgeRelationStep kind={kind} variants={variants.data} />
        </section>
        <section hidden={step !== 1}>
          <KnowledgeRuleStep
            kind={kind}
            quantitySource={quantitySource}
            summary={summary}
          />
        </section>
        <section hidden={step !== 2}>
          <ReviewStep kind={kind} summary={summary} />
          <EvidenceReferenceFields />
          <Alert type="info" title={`本条关系覆盖 ${matchingConfigurations(values ?? initial ?? {}, variants.data ?? []).length} 个配置`} description={matchingConfigurations(values ?? initial ?? {}, variants.data ?? []).map(v => `${v.product.model} · ${v.name}`).join("；")} />
        </section>
        </div><aside><Typography.Title level={5}>原文资料与引用</Typography.Title><SourceEvidencePanel variants={matchingConfigurations(values ?? initial ?? {}, variants.data ?? [])} /></aside></div>
      </Form>
    </Modal>
  );
}

function ReviewStep({ kind, summary }: { kind?: Knowledge["kind"]; summary: string }) {
  return (
    <>
      <KnowledgeSentence summary={summary} />
      <Form.Item name="name" label="知识名称（不填会根据上面的关系自动生成）">
        <Input placeholder="便于以后搜索和识别" />
      </Form.Item>
      <Form.Item name="status" label="本次保存状态">
        <Select
          options={[
            { value: "draft", label: "草稿：信息可以不完整，不参与自动通过" },
            { value: "confirmed", label: "已确认：有依据，参与项目检查" },
            { value: "disabled", label: "停用：不参与检查" },
          ]}
        />
      </Form.Item>
      {kind === "accessory" ? (
        <Typography.Paragraph type="secondary">
          可以确认配套关系，数量或候选尚未确认时将保留待办，不能应用补料。
        </Typography.Paragraph>
      ) : null}
      <AuthorFields />
    </>
  );
}

function firstStepFields(kind?: Knowledge["kind"]) {
  const common: (string | (string | number)[])[] = ["kind", ["selector", "variant_ids"]];
  if (kind === "suitability") return [...common, "system", "role", "role_id"];
  if (kind === "accessory") return [...common, "need_name"];
  if (kind === "sharing") return [...common, "shared_role_refs"];
  return common;
}

function errorStep(names: (string | number)[][]) {
  const roots = new Set(names.map((name) => String(name[0])));
  if (
    ["kind", "selector", "system", "role", "need_name", "target_variant_ids", "shared_roles", "shared_role_refs", "role_id", "system_definition_id"].some(
      (name) => roots.has(name),
    )
  ) {
    return 0;
  }
  if (
    ["conditions", "calculation_scope", "quantity_source", "quantity_key", "mode", "factor"].some(
      (name) => roots.has(name),
    )
  ) {
    return 1;
  }
  return 2;
}
