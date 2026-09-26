import { useMemo } from "react";
import { AutoComplete, Space, Typography } from "antd";
import { useKnowledge, useVariants } from "./shared";

export function SystemTypeInput({
  id,
  value,
  onChange,
  placeholder,
}: {
  id?: string;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
}) {
  const variants = useVariants();
  const knowledge = useKnowledge();
  const names = useMemo(
    () =>
      [
        ...new Set([
          ...(variants.data?.flatMap((item) => item.systems) ?? []),
          ...(knowledge.data
            ?.filter((item) => item.status !== "disabled")
            .map((item) => item.system) ?? []),
          value ?? "",
        ]),
      ].filter(Boolean).sort(),
    [knowledge.data, value, variants.data],
  );
  const error = variants.error ?? knowledge.error;
  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <AutoComplete
        id={id}
        value={value}
        onChange={onChange}
        allowClear
        style={{ width: "100%" }}
        placeholder={placeholder ?? "选择具体系统版本，也可输入新版本"}
        options={names.map((name) => ({ value: name }))}
        filterOption={(input, option) => (option?.value ?? "").includes(input)}
        status={error ? "error" : undefined}
      />
      {error ? (
        <Typography.Text type="danger">
          版本选项加载失败：{error.message}
        </Typography.Text>
      ) : null}
    </Space>
  );
}
