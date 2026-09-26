import { Button, Card, Space, Tree } from "antd";
import type { TreeDataNode } from "antd";
import type { Requirement } from "../types";

export function ProjectSystemPanel({
  tree,
  requirement,
  selectedSystem,
  busy,
  onAddSystem,
  onAddRequirement,
  onSelectSystem,
  onSelectRequirement,
  onEditRequirement,
  onUnlinkRequirement,
}: {
  tree: TreeDataNode[];
  requirement?: Requirement;
  selectedSystem?: string;
  busy: boolean;
  onAddSystem: () => void;
  onAddRequirement: (systemId: string) => void;
  onSelectSystem: (id: string) => void;
  onSelectRequirement: (id: string) => void;
  onEditRequirement: (requirement: Requirement) => void;
  onUnlinkRequirement: (requirement: Requirement) => void;
}) {
  return (
    <Card title="房间与系统">
      <Space orientation="vertical">
        <Button disabled={busy} onClick={onAddSystem}>
          添加房间 / 系统
        </Button>
        <Button
          disabled={!selectedSystem || busy}
          onClick={() => onAddRequirement(selectedSystem!)}
        >
          添加角色需求
        </Button>
      </Space>
      <Tree
        treeData={tree}
        defaultExpandAll
        onSelect={(keys) => {
          const [type, id] = String(keys[0] ?? "").split(":");
          if (type === "system") onSelectSystem(id);
          if (type === "requirement") onSelectRequirement(id);
        }}
      />
      {requirement ? (
        <Space wrap>
          <Button onClick={() => onEditRequirement(requirement)}>编辑需求</Button>
          <Button onClick={() => onUnlinkRequirement(requirement)}>解除设备关联</Button>
        </Space>
      ) : null}
    </Card>
  );
}
