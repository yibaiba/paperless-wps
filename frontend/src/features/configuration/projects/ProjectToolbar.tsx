import { Button, Space, Typography } from "antd";
import { ProjectHistory } from "./ProjectHistory";

export function ProjectToolbar({
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
}: {
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
}) {
  return (
    <Space wrap>
      <Button onClick={onClose}>返回项目</Button>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {name} · 配置
      </Typography.Title>
      <span>{dirty ? "有未保存修改" : `已保存 v${revision}`}</span>
      <Button type="primary" onClick={onSave} loading={saving} disabled={busy}>
        保存项目版本
      </Button>
      <Button onClick={onAuthor}>维护信息</Button>
      <ProjectHistory entityId={entityId} />
      <Button disabled={!canUndo || busy} onClick={onUndo}>
        撤销
      </Button>
      <Button disabled={!canRedo || busy} onClick={onRedo}>
        重做
      </Button>
      <Button onClick={onImport}>导入旧清单 / 拓扑</Button>
    </Space>
  );
}
