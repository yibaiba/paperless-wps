import { useQuery } from "@tanstack/react-query";
import { AutoComplete, Space, Typography } from "antd";
import { api } from "../../shared/api";
import { ROOT } from "./shared";
import type { Knowledge } from "./types";

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
  const knowledge = useQuery({
    queryKey: ["configuration", "knowledge"],
    queryFn: () => api<Knowledge[]>(ROOT + "/knowledge"),
  });
  const roles = [
    ...new Set(
      knowledge.data
        ?.filter(
          (k) =>
            k.system === system &&
            k.kind === "suitability" &&
            k.status !== "disabled",
        )
        .map((k) => k.role) ?? [],
    ),
  ];
  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <AutoComplete
        id={id}
        value={value}
        onChange={onChange}
        style={{ width: "100%" }}
        placeholder="选择本版本已有角色，也可输入新角色"
        options={roles.sort().map((role) => ({ value: role }))}
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
