import type { Definitions, IssueAction, System, SystemDefinition } from '../types';

export function selectedDefinition(system: Pick<System, 'definition_id' | 'knowledge_package_id'>, definitions?: Definitions) {
  const bundle = definitions?.packages.find(p => p.id === system.knowledge_package_id);
  return bundle?.definition ?? definitions?.definitions.find(d => d.id === system.definition_id);
}

export function requiredRoleLabel(role: SystemDefinition['roles'][number], status: SystemDefinition['status']) {
  if (status !== 'confirmed') return role.feature ? `启用「${role.feature}」时核对必要性` : '必要性待核对';
  if (role.feature) return `启用「${role.feature}」时${role.required ? '必需' : '可选'}`;
  return role.required ? '基础必需角色' : '可选角色';
}

export function requestedRole(action: IssueAction) {
  return action.role_id && action.role_name ? { id: action.role_id, name: action.role_name } : undefined;
}
