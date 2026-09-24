import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Drawer, Form, Space, Table, Typography } from "antd";
import { api } from "../../shared/api";
import { AttributeEditor, cleanAttributes, ROOT, Status } from "./shared";
import { EvidenceDetails } from "./EvidenceDetails";
import type { Attribute, Candidate, Knowledge } from "./types";

export function KnowledgeTrial({
  knowledge,
  onClose,
}: {
  knowledge: Knowledge;
  onClose: () => void;
}) {
  const fields = [
    ...new Map(
      knowledge.conditions
        .filter((c) => c.field.startsWith("project."))
        .map((c) => [
          c.field,
          {
            key: c.field.slice("project.".length),
            kind:
              c.operator === "range"
                ? c.unit
                  ? "quantity"
                  : "number"
                : "text",
            unit: c.unit,
            value: null,
          },
        ]),
    ).values(),
  ];
  const trial = useMutation({
    mutationFn: (environment: Attribute[]) =>
      api<Candidate[]>(ROOT + "/candidates", {
        method: "POST",
        body: JSON.stringify({
          system: knowledge.system,
          role: knowledge.role,
          environment: cleanAttributes(environment),
        }),
      }),
  });
  const results = trial.data?.filter(
    (item) =>
      !knowledge.selector.exclude_variant_ids.includes(item.variant.id) &&
      (!knowledge.selector.variant_ids.length ||
        knowledge.selector.variant_ids.includes(item.variant.id)) &&
      (!knowledge.selector.category ||
        item.variant.product.category === knowledge.selector.category) &&
      (!knowledge.selector.series.length ||
        item.variant.series.some((s) => knowledge.selector.series.includes(s))),
  );
  return (
    <Drawer open width={900} title="试用搭配知识" onClose={onClose}>
      <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
        <Typography.Text strong>
          {knowledge.system} / {knowledge.role}
        </Typography.Text>
        <Alert
          type="info"
          showIcon
          title="填写实际需求，运行与项目选型相同的检查。"
          description="这里只检查，不保存项目或加入清单。留空会显示资料不足；草稿和停用规则不参与计算。"
        />
        <Typography.Paragraph>{knowledge.evidence}</Typography.Paragraph>
        <Form
          layout="vertical"
          disabled={trial.isPending}
          initialValues={{ environment: fields }}
          onValuesChange={() => trial.reset()}
          onFinish={(values) => trial.mutate(values.environment ?? [])}
        >
          <AttributeEditor name="environment" />
          <Button type="primary" htmlType="submit" loading={trial.isPending}>
            检查候选
          </Button>
        </Form>
        {trial.error ? (
          <Alert type="error" title={trial.error.message} />
        ) : null}
        {trial.data ? (
          <Table<Candidate>
            size="small"
            rowKey={(item) => item.variant.id}
            dataSource={results}
            columns={[
              {
                title: "产品 / 配置",
                render: (_, item) =>
                  `${item.variant.product.model} · ${item.variant.name}`,
              },
              {
                title: "结果",
                width: 140,
                render: (_, item) => <Status value={item.status} />,
              },
            ]}
            expandable={{
              expandedRowRender: (item) =>
                item.evidence.length ? (
                  <Space orientation="vertical">
                    {item.evidence.map((e, i) => (
                      <EvidenceDetails key={i} evidence={e} />
                    ))}
                  </Space>
                ) : (
                  "没有匹配当前系统版本与角色的已确认知识，不能据此判定兼容。"
                ),
            }}
          />
        ) : null}
      </Space>
    </Drawer>
  );
}
