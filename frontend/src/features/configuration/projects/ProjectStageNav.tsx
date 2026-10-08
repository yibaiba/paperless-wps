import { Segmented, Space, Typography } from "antd";

export type ProjectStage = "requirements" | "configuration" | "quotation";

const descriptions: Record<ProjectStage, string> = {
  requirements: "确认房间、系统版本、功能、规模和环境",
  configuration: "选择设备与配套，核对用途、供货和拓扑",
  quotation: "采用价格、检查报价并生成公司模板",
};

export function ProjectStageNav({
  value,
  onChange,
  onPreloadQuotation,
}: {
  value: ProjectStage;
  onChange: (value: ProjectStage) => void;
  onPreloadQuotation: () => void;
}) {
  return <div className="project-stage-nav">
    <Segmented<ProjectStage>
      block
      value={value}
      onChange={onChange}
      options={[
        { value: "requirements", label: "1 需求与系统" },
        { value: "configuration", label: "2 配置与配套" },
        { value: "quotation", label: <span onMouseEnter={onPreloadQuotation} onFocus={onPreloadQuotation}>3 报价与导出</span> },
      ]}
    />
    <Space><Typography.Text type="secondary">{descriptions[value]}</Typography.Text></Space>
  </div>;
}
