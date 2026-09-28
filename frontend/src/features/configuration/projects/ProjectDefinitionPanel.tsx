import { Alert, Card, Select, Space, Typography } from "antd";
import type { Configuration } from "../types";
import { useDefinitions } from "../knowledge/useDefinitions";

export function ProjectDefinitionPanel({ configuration, onApply }: { configuration: Configuration; onApply: (next: Configuration) => void }) {
  const definitions = useDefinitions(configuration.definition_snapshot_id);
  return <Space orientation="vertical" style={{ width: "100%" }} size="middle">
    <Alert showIcon type="info" title="关联系统定义与知识包" description="选择具体定义后，必要角色与知识覆盖才有核对依据。历史项目的映射由你明确选择。" />
    {definitions.error ? <Alert type="error" title={definitions.error.message} /> : null}
    {configuration.systems.map((system) => {
      const definition = definitions.data?.definitions.find((d) => d.id === system.definition_id);
      return <Card key={system.id} title={system.name} size="small">
        <Space orientation="vertical" style={{ width: "100%" }}>
          <Typography.Text>系统版本定义</Typography.Text>
          <Select style={{ width: "100%" }} value={system.definition_id || undefined} placeholder="明确选择对应版本"
            options={definitions.data?.definitions.map((d) => ({ value: d.id, label: d.name }))}
            onChange={(id) => onApply({ ...configuration, definition_snapshot_id: null,
              systems: configuration.systems.map((s) => s.id === system.id ? { ...s, definition_id: id, kind: definitions.data!.definitions.find((d) => d.id === id)!.name, knowledge_package_id: "" } : s),
              requirements: configuration.requirements.map((r) => r.system_id === system.id ? { ...r, role_id: "" } : r),
            })} />
          <Typography.Text>已发布知识包</Typography.Text>
          <Select style={{ width: "100%" }} allowClear value={system.knowledge_package_id || undefined} placeholder="选择固定修订"
            options={definitions.data?.packages.filter((p) => p.system_definition_id === system.definition_id).map((p) => ({ value: p.id, label: `${p.name} · ${p.branch} · v${p.revision}` }))}
            onChange={(id) => onApply({ ...configuration, definition_snapshot_id: null, systems: configuration.systems.map((s) => s.id === system.id ? { ...s, knowledge_package_id: id ?? "" } : s) })} />
          <Typography.Text>本次选择的功能</Typography.Text>
          <Select mode="multiple" style={{ width: "100%" }} value={system.features ?? []}
            options={[...new Set(definition?.roles.map((r) => r.feature).filter(Boolean))].map((f) => ({ value: f, label: f }))}
            onChange={(features) => onApply({ ...configuration, systems: configuration.systems.map((s) => s.id === system.id ? { ...s, features } : s) })} />
          {configuration.requirements.filter((r) => r.system_id === system.id).map((r) => <div key={r.id}>
            <Typography.Text>{r.role} 对应的定义角色</Typography.Text>
            <Select style={{ width: "100%" }} value={r.role_id || undefined} options={definition?.roles.map((role) => ({ value: role.id, label: role.name }))}
              onChange={(roleId) => onApply({ ...configuration, requirements: configuration.requirements.map((item) => item.id === r.id ? { ...item, role_id: roleId, role: definition!.roles.find((role) => role.id === roleId)!.name } : item) })} />
          </div>)}
        </Space>
      </Card>;
    })}
  </Space>;
}
