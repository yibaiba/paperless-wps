import { Alert, Collapse, Form, Input, Select } from "antd";
import { ConditionsEditor } from "./ConditionsEditor";
import { useDefinitions } from "./useDefinitions";
import { useVariants, variantOptions } from "../shared";

export function KnowledgeIdentityFields() {
  const definitions = useDefinitions();
  const variants = useVariants();
  const form = Form.useFormInstance();
  const identity = Form.useWatch("system_definition_id", form);
  const kind = Form.useWatch("kind", form);
  const definition = definitions.data?.definitions.find((d) => d.id === identity);
  return <>
    {definitions.error ? <Alert type="error" title={definitions.error.message} /> : null}
    <Collapse items={[
      { key: "identity", label: "关联系统定义与角色", children: <>
        <Form.Item name="system_definition_id" label="系统版本定义">
          <Select allowClear options={definitions.data?.definitions.map((d) => ({ value: d.id, label: d.name }))}
            onChange={(id) => { form.setFieldValue("role_id", ""); form.setFieldValue("system", definitions.data?.definitions.find((d) => d.id === id)?.name ?? ""); }} />
        </Form.Item>
        <Form.Item name="role_id" label="角色标识">
          <Select allowClear options={definition?.roles.map((r) => ({ value: r.id, label: r.name }))}
            onChange={(id) => form.setFieldValue("role", definition?.roles.find((r) => r.id === id)?.name ?? "")} />
        </Form.Item>
      </> },
      { key: "activation", label: "仅在特定环境下启用这条关系", children: <ConditionsEditor name="activation_conditions" /> },
      ...(kind === "suitability" ? [{ key: "alternatives", label: "替代分支组", children:
        <Form.Item name="alternative_group" label="同组分支满足其一即可" extra="仅将明确可以替代的适用关系放入同组，其他约束仍需同时满足。"><Input /></Form.Item>
      }] : []),
      { key: "scope", label: "共性知识的依据范围", children: <>
        <Form.Item name="scope_basis" label="原资料覆盖范围"><Select options={[
          { value: "listed_configurations", label: "仅覆盖已核对的具体配置" },
          { value: "entire_scope", label: "依据明确覆盖整个所选系列或类别" },
        ]} /></Form.Item>
        <Form.Item name="reviewed_variant_ids" label="已核对配置"><Select mode="multiple" options={variantOptions(variants.data)} /></Form.Item>
      </> },
    ]} />
  </>;
}
