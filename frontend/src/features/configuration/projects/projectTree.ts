import type { Configuration, Requirement, System } from "../types";

export interface ProjectTreeNode {
  key: string;
  title: string;
  children?: ProjectTreeNode[];
}

const UNASSIGNED_ROOM = "__unassigned__";

export function buildProjectTree(
  configuration: Configuration,
): ProjectTreeNode[] {
  const requirementsBySystem = groupRequirements(configuration.requirements);
  const systemsByRoom = groupSystems(configuration.systems);
  const rooms = configuration.rooms.map((room) => ({
    key: "room:" + room.id,
    title: room.name,
    children: (systemsByRoom.get(room.id) ?? []).map((system) =>
      systemNode(system, requirementsBySystem, true),
    ),
  }));
  return [
    ...rooms,
    {
      key: "room:unassigned",
      title: "未分房间",
      children: (systemsByRoom.get(UNASSIGNED_ROOM) ?? []).map((system) =>
        systemNode(system, requirementsBySystem, false),
      ),
    },
  ];
}

function groupRequirements(requirements: Requirement[]) {
  const grouped = new Map<string, Requirement[]>();
  for (const requirement of requirements) {
    const items = grouped.get(requirement.system_id) ?? [];
    items.push(requirement);
    grouped.set(requirement.system_id, items);
  }
  return grouped;
}

function groupSystems(systems: System[]) {
  const grouped = new Map<string, System[]>();
  for (const system of systems) {
    const roomId = system.room_id ?? UNASSIGNED_ROOM;
    const items = grouped.get(roomId) ?? [];
    items.push(system);
    grouped.set(roomId, items);
  }
  return grouped;
}

function systemNode(
  system: System,
  requirementsBySystem: Map<string, Requirement[]>,
  showSelection: boolean,
): ProjectTreeNode {
  return {
    key: "system:" + system.id,
    title: system.name,
    children: (requirementsBySystem.get(system.id) ?? []).map((requirement) => ({
      key: "requirement:" + requirement.id,
      title:
        requirement.role +
        (showSelection
          ? requirement.device_id
            ? " · 已选"
            : " · 待选"
          : ""),
    })),
  };
}
