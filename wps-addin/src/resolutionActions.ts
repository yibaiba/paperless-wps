import type { ResolutionAction } from './businessTypes';
import type { HostAdapter } from './host';
import type { WorkbookMetadata } from './types';

const KINDS = new Set(['locate_row', 'confirm_identity', 'check_source', 'edit_business', 'review_knowledge']);

export function resolutionActions(issue: unknown): ResolutionAction[] {
  if (!issue || typeof issue !== 'object' || !('resolution_actions' in issue)) return [];
  if (!Array.isArray(issue.resolution_actions)) throw new Error('问题处理动作协议不正确');
  return issue.resolution_actions.map(validateAction);
}

function validateAction(value: unknown): ResolutionAction {
  if (!value || typeof value !== 'object') throw new Error('问题处理动作缺少目标');
  const action = value as ResolutionAction;
  if (!KINDS.has(action.kind) || !action.sheet || !action.binding_id || !action.context_fingerprint
    || !Number.isSafeInteger(action.row) || action.row < 1
    || !Number.isSafeInteger(action.column) || action.column < 1
    || !Number.isSafeInteger(action.expected_local_revision)
    || !Number.isSafeInteger(action.template_profile_revision)) throw new Error('问题处理动作协议不正确');
  return action;
}

export function requestedResolution(raw: string): ResolutionAction | undefined {
  return raw.startsWith('{') ? validateAction(JSON.parse(raw)) : undefined;
}

export function assertResolutionCurrent(options: {
  action: ResolutionAction; metadata: WorkbookMetadata; revision: number; fingerprint?: string;
}) {
  const { action, metadata, revision, fingerprint } = options;
  if (metadata.binding?.binding_id !== action.binding_id
    || metadata.profile_revision !== action.template_profile_revision
    || revision !== action.expected_local_revision
    || (fingerprint !== undefined && fingerprint !== action.context_fingerprint)) {
    throw new Error('问题上下文已变化，请重新预览再处理');
  }
}

export function navigateResolution(options: {
  host: HostAdapter; action: ResolutionAction; fingerprint: string;
}) {
  const { host, action, fingerprint } = options;
  assertResolutionCurrent({ action, metadata: host.readMetadata(), revision: host.businessRevision(), fingerprint });
  host.selectCell(action);
  host.hideInlineEditor();
  if (action.kind !== 'locate_row') host.openTaskPaneAction(JSON.stringify(action));
}
