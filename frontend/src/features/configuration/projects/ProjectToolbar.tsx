import { useState, type ReactNode } from "react";
import { Button, Drawer, Space, Typography } from "antd";
import { ProjectHistory } from "./ProjectHistory";

export function ProjectToolbar({
  projectId,
  name,
  revision,
  dirty,
  busy,
  saving,
  canUndo,
  canRedo,
  entityId,
  onClose,
  onSave,
  onAuthor,
  onUndo,
  onRedo,
  onImport,
  onView,
  secondaryActions,
  proposalAction,
}: {
  projectId: string;
  name: string;
  revision: number;
  dirty: boolean;
  busy: boolean;
  saving: boolean;
  canUndo: boolean;
  canRedo: boolean;
  entityId?: string;
  onClose: () => void;
  onSave: () => void;
  onAuthor: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onImport: () => void;
  onView: (tab: string) => void;
  secondaryActions: ReactNode;
  proposalAction?: ReactNode;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  return (
    <div className="project-toolbar">
      <div className="project-toolbar-heading">
        <Button type="text" onClick={onClose}>返回项目</Button>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>{name}</Typography.Title>
          <Typography.Text type="secondary">{dirty ? "有未保存到项目版本的修改" : `已保存 v${revision}`}</Typography.Text>
        </div>
      </div>
      <Space wrap>
      {proposalAction}
      <Button disabled={!canUndo || busy} onClick={onUndo}>撤销</Button>
      <Button disabled={!canRedo || busy} onClick={onRedo}>重做</Button>
      <Button onClick={() => setMoreOpen(true)}>高级与维护</Button>
      <Drawer open={moreOpen} onClose={() => setMoreOpen(false)} placement="right" title="高级与维护">
        <Space orientation="vertical" className="project-secondary-actions" onClick={() => setMoreOpen(false)}>
          <Button onClick={onAuthor}>维护信息</Button>
          <ProjectHistory entityId={entityId} projectId={projectId} />
          <Button onClick={onImport}>导入旧清单 / 拓扑</Button>
          <Button onClick={() => onView("definitions")}>系统版本与角色</Button>
          <Button onClick={() => onView("output")}>设备与采购明细</Button>
          {secondaryActions}
        </Space>
      </Drawer>
      <Button type="primary" onClick={onSave} loading={saving} disabled={busy}>
        保存版本
      </Button>
      </Space>
    </div>
  );
}
