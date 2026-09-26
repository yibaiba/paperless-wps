import { useMemo } from "react";
import { AutoComplete, Space, Typography } from "antd";
import { useKnowledge } from "./shared";

export function RoleInput({
  system,
  id,
  value,
  onChange,
}: {
  system: string;
  id?: string;
  value?: string;
  onChange?: (value: string) => void;
}) {
  const knowledge = useKnowledge();
  const roles = useMemo(
    () =>
      [
        ...new Set(
          knowledge.data
            ?.filter(
              (item) =>
                item.system === system &&
                item.kind === "suitability" &&
                item.status !== "disabled",
            )
            .map((item) => item.role) ?? [],
        ),
      ].sort(),
    [knowledge.data, system],
  );
  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <AutoComplete
        id={id}
        value={value}
        onChange={onChange}
        style={{ width: "100%" }}
        placeholder="选择本版本已有角色，也可输入新角色"
        options={roles.map((role) => ({ value: role }))}
        filterOption={(input, option) => (option?.value ?? "").includes(input)}
      />
      {knowledge.error ? (
        <Typography.Text type="danger">
          角色加载失败：{knowledge.error.message}
        </Typography.Text>
      ) : null}
    </Space>
  );
}
