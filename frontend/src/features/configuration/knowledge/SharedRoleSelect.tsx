import { Select } from "antd";
import { useDefinitions } from "./useDefinitions";

type RoleRef = { system_definition_id: string; role_id: string };
const key = (value: RoleRef) => JSON.stringify([value.system_definition_id, value.role_id]);

export function SharedRoleSelect({ value = [], onChange }: {
  value?: RoleRef[]; onChange?: (value: RoleRef[]) => void;
}) {
  const query = useDefinitions();
  const options = query.data?.definitions.flatMap((definition) => definition.roles.map((role) => ({
    value: key({ system_definition_id: definition.id, role_id: role.id }),
    label: `${definition.name} / ${role.name}`,
  })));
  return <Select mode="multiple" showSearch optionFilterProp="label" loading={query.isLoading}
    value={value.map(key)} options={options} onChange={(values) => onChange?.(values.map((value) => {
      const [system_definition_id, role_id] = JSON.parse(value) as [string, string];
      return { system_definition_id, role_id };
    }))} />;
}
