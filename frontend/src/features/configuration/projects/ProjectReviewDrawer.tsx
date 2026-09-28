import type { ComponentProps } from "react";
import { Alert, Drawer, Tabs } from "antd";
import { ProjectChecks } from "../ProjectChecks";
import { ProjectOpenItems } from "./ProjectOpenItems";

type Props = ComponentProps<typeof ProjectChecks> & {
  open: boolean;
  activeTab: string;
  onClose: () => void;
  onTabChange: (tab: string) => void;
  onAction: ComponentProps<typeof ProjectOpenItems>["onAction"];
};

export function ProjectReviewDrawer({ open, activeTab, onClose, onTabChange, onAction, ...checks }: Props) {
  return <Drawer title="检查与配套" open={open} onClose={onClose} size={960}>
    {checks.stale ? <Alert type="warning" showIcon title="配置已变化，下方为上次结果，请重新检查。" /> : null}
    <Tabs activeKey={activeTab} onChange={onTabChange} items={[
      { key: "todo", label: "待处理事项", children: <ProjectOpenItems
        checked={checks.checked} configuration={checks.configuration} onAction={onAction}
      /> },
      { key: "accessories", label: "选择配套", children: <ProjectChecks {...checks} section="accessories" /> },
      { key: "checks", label: "检查详情与依据", children: <ProjectChecks {...checks} section="checks" /> },
    ]} />
  </Drawer>;
}
