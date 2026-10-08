import { useEffect, useReducer, useRef, useState } from 'react';
import { useBlocker, useSearchParams } from 'react-router-dom';
import { App } from 'antd';
import { api, ApiError } from '../../../../shared/api';
import type { Checked, Configuration, ProjectConfiguration } from '../../types';
import type { EditPreview } from '../../quotation/sheet/useSheetEditing';
import type { EditOperation } from '../../quotation/sheet/model';
import { type Operation, configurationOperations } from './operations';
import { createSaveTransaction } from './saveTransaction';
import { mergeDelta, post, writeRequest, type Delta, type Workspace } from './transport';
import { configurationKey } from '../configurationIdentity';

const key = (config: Configuration, historyKey = '') => configurationKey(config) + historyKey;
type SyncPhase = 'idle' | 'creating' | 'syncing' | 'failed' | 'conflict';
interface SyncState { phase: SyncPhase; error: string }
type SyncAction =
  | { type: 'start'; creating: boolean }
  | { type: 'success' }
  | { type: 'failure'; error: string; conflict: boolean };
const syncReducer = (_state: SyncState, action: SyncAction): SyncState => {
  if (action.type === 'start') return { phase: action.creating ? 'creating' : 'syncing', error: '' };
  if (action.type === 'success') return { phase: 'idle', error: '' };
  return { phase: action.conflict ? 'conflict' : 'failed', error: action.error };
};
export interface RecheckInput {
  expected_project_revision: number; fingerprint: string; refresh_knowledge: boolean;
  upgrade_calculation: boolean; upgrade_decisions: boolean; cleanup_allocations: boolean;
}
interface Options {
  projectId: string; saved: ProjectConfiguration; configuration: Configuration;
  initialWorkspace?: Workspace; historyKey?: string; acceptCheckpoint?: (checked: Checked, key: string) => void; accept: (checked: Checked) => void; acceptOperation: (checked: Checked) => void;
}
export function usePersistentDraft(options: Options) {
  const live = useRef(options); live.current = options;
  const [, setParams] = useSearchParams();
  const remote = useRef<Workspace | undefined>(options.initialWorkspace);
  const synced = useRef(key(options.initialWorkspace?.configuration ?? options.saved.configuration, options.historyKey));
  const checkpoints = useRef(new Map<string, number>(options.initialWorkspace ? [[key(options.initialWorkspace.configuration, options.historyKey), options.initialWorkspace.revision]] : []));
  const pending = useRef<(() => Promise<Workspace>) | undefined>(undefined);
  const operationPending = useRef(false);
  const checkpointPending = useRef(false);
  const pendingKey = useRef<string | undefined>(undefined);
  const rejectedProjection = useRef<string | undefined>(undefined);
  const creating = useRef<Promise<Workspace> | undefined>(undefined);
  const running = useRef(false), alive = useRef(true);
  const [syncState, dispatchSync] = useReducer(syncReducer, { phase: 'idle', error: '' });
  const { error, phase } = syncState;
  const syncing = phase === 'creating' || phase === 'syncing';
  const [, render] = useState(0);
  const { modal } = App.useApp();
  const creationId = useRef(crypto.randomUUID());
  const currentKey = key(options.configuration, options.historyKey);
  // An unacknowledged command may not have changed the local projection yet.
  const unsynced = currentKey !== synced.current || Boolean(pending.current);
  const saveTransaction = useRef<ReturnType<typeof createSaveTransaction> | undefined>(undefined);
  saveTransaction.current ??= createSaveTransaction({
    post, newId: () => crypto.randomUUID(),
    isRejected: (cause) => cause instanceof ApiError && (cause.status === 409 || cause.status === 422),
    readWorkspace: (id) => api<Workspace>('/work-drafts/' + id),
    readProject: () => api<ProjectConfiguration>('/configuration/projects/' + live.current.projectId),
    acceptWorkspace: (workspace) => { remote.current = workspace; },
  });
  const ensure = async () => {
    await saveTransaction.current!.settle();
    if (remote.current) return remote.current;
    const current = live.current;
    creating.current ??= post<Workspace>('/work-drafts', { project_id: current.projectId,
      expected_revision: current.saved.revision, operation_id: creationId.current }).finally(() => { creating.current = undefined; });
    const workspace = await creating.current;
    remote.current = workspace;
    checkpoints.current.set(synced.current, workspace.revision);
    if (alive.current) setParams((previous) => { const next = new URLSearchParams(previous); next.set('draft', workspace.id); return next; }, { replace: true });
    return workspace;
  };
  const synchronize = async () => {
    if (running.current) return;
    running.current = true; rejectedProjection.current = undefined;
    dispatchSync({ type: 'start', creating: !remote.current });
    const target = live.current.configuration, targetKey = key(target, live.current.historyKey);
    try {
      const workspace = await ensure();
      if (!pending.current) {
        pendingKey.current = targetKey;
        const checkpoint = checkpoints.current.get(targetKey);
        if (checkpoint) {
          const request = { draft_id: workspace.id, expected_revision: workspace.revision,
            operation_id: crypto.randomUUID(), checkpoint_revision: checkpoint };
          pending.current = () => post<Workspace>(`/work-drafts/${workspace.id}/restore`, request);
        } else {
          const operations = configurationOperations(workspace.configuration, target);
          if (!operations.length) {
            if (targetKey !== key(workspace.configuration, live.current.historyKey)) throw new Error("草稿包含未转换为业务操作的变化，尚未同步；请保留页面并核对。");
            synced.current = targetKey;
            dispatchSync({ type: 'success' });
            return;
          }
          const request = writeRequest(workspace, operations);
          pending.current = async () => mergeDelta(workspace, await post<Delta>(`/work-drafts/${workspace.id}/edit`, request));
        }
      }
      const result = await pending.current();
      const appliedKey = pendingKey.current!;
      const wasOperation = operationPending.current, wasCheckpoint = checkpointPending.current;
      operationPending.current = false; checkpointPending.current = false;
      pending.current = undefined; pendingKey.current = undefined; remote.current = result;
      if (!wasOperation) checkpoints.current.set(appliedKey, result.revision);
      if (!wasCheckpoint) checkpoints.current.set(key(result.configuration, live.current.historyKey), result.revision);
      synced.current = appliedKey;
      if (alive.current && key(live.current.configuration, live.current.historyKey) === appliedKey) {
        synced.current = key(result.configuration, live.current.historyKey);
        if (wasCheckpoint) acceptCheckpoint(result);
        else if (wasOperation) live.current.acceptOperation(result.checked);
        else live.current.accept(result.checked);
      }
      if (alive.current) dispatchSync({ type: 'success' });
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422 && !operationPending.current) rejectedProjection.current = pendingKey.current;
      if (cause instanceof ApiError && (cause.status === 422 || cause.status === 409)) { pending.current = undefined; pendingKey.current = undefined; operationPending.current = false; checkpointPending.current = false; }
      if (alive.current) dispatchSync({ type: 'failure', error: cause instanceof Error ? cause.message : String(cause),
        conflict: cause instanceof ApiError && cause.status === 409 });
    }
    finally { running.current = false; if (alive.current) render((v) => v + 1); }
  };
  useEffect(() => {
    if (unsynced && !syncing && !error) void synchronize();
  }, [currentKey, syncing, error]); // Each accepted UI edit is one persisted checkpoint.
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (unsynced || syncing) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [unsynced, syncing]);
  const blocker = useBlocker(({ currentLocation, nextLocation, historyAction }) =>
    (unsynced || syncing) && (currentLocation.pathname !== nextLocation.pathname || (historyAction === "POP" && currentLocation.search !== nextLocation.search)));
  useEffect(() => {
    if (blocker.state !== 'blocked') return;
    const dialog = modal.confirm({ title: '还有未同步的草稿修改', content: '留在页面重试同步，或明确放弃尚未同步的修改。',
      okText: '留在页面', cancelText: '放弃并离开', onOk: () => blocker.reset(), onCancel: () => blocker.proceed() });
    return () => dialog.destroy();
  }, [blocker.state]);
  const preview = async (operations: EditOperation[], version: number) => {
    if (running.current || pending.current || key(live.current.configuration, live.current.historyKey) !== synced.current) throw new Error('草稿尚未同步，请先完成同步或重试。');
    const workspace = await ensure();
    const result = await post<Delta & { draft_version: number }>(`/work-drafts/${workspace.id}/preview`, { expected_revision: workspace.revision, draft_version: version, operations });
    return { draft_version: result.draft_version, checked: mergeDelta(workspace, { ...result, revision: workspace.revision }).checked, changes: [] } as EditPreview;
  };
  const save = async () => {
    if (running.current || pending.current || key(live.current.configuration, live.current.historyKey) !== synced.current) throw new Error('草稿尚未同步，请先重试同步。');
    const workspace = await ensure();
    return saveTransaction.current!.save(workspace);
  };
  const readyWorkspace = async () => {
    if (running.current || pending.current || key(live.current.configuration, live.current.historyKey) !== synced.current) throw new Error('草稿尚未同步，请完成同步后生成方案。');
    return ensure();
  };
  const executeWrite = async (operations: Operation[], adoption?: RecheckInput) => {
    if (running.current || pending.current || key(live.current.configuration, live.current.historyKey) !== synced.current) throw new Error('草稿尚未同步，请完成同步后编辑。');
    // Reserve the draft before ensure() yields to another event handler.
    running.current = true; rejectedProjection.current = undefined;
    dispatchSync({ type: 'start', creating: !remote.current });
    const beforeKey = key(live.current.configuration, live.current.historyKey);
    pendingKey.current = beforeKey; operationPending.current = true; checkpointPending.current = Boolean(adoption);
    let workspace: Workspace | undefined;
    let request: Record<string, unknown> | undefined;
    // Keep the command even if creating the work draft loses its response.
    pending.current = async () => {
      workspace ??= await ensure();
      request ??= adoption ? { draft_id: workspace.id, expected_revision: workspace.revision,
        operation_id: crypto.randomUUID(), ...adoption } : writeRequest(workspace, operations);
      checkpoints.current.set(beforeKey, workspace.revision);
      return adoption
        ? post<Workspace>(`/work-drafts/${workspace.id}/recheck`, request)
        : mergeDelta(workspace, await post<Delta>(`/work-drafts/${workspace.id}/edit`, request));
    };
    try {
      const result = await pending.current();
      remote.current = result; pending.current = undefined; pendingKey.current = undefined; operationPending.current = false; checkpointPending.current = false;
      if (!adoption) checkpoints.current.set(key(result.configuration, live.current.historyKey), result.revision);
      synced.current = key(result.configuration, live.current.historyKey);
      if (key(live.current.configuration, live.current.historyKey) !== beforeKey) throw new Error('采用期间本地已变化，提案已同步但未覆盖本地编辑，请恢复草稿核对。');
      if (adoption) acceptCheckpoint(result);
      dispatchSync({ type: 'success' });
      return result.checked;
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 422 || cause.status === 409)) { pending.current = undefined; pendingKey.current = undefined; operationPending.current = false; checkpointPending.current = false; }
      dispatchSync({ type: 'failure', error: cause instanceof Error ? cause.message : String(cause),
        conflict: cause instanceof ApiError && cause.status === 409 });
      throw cause;
    } finally { running.current = false; render(v => v + 1); }
  };
  const check = async (refreshKnowledge: boolean) => {
    if (running.current || pending.current || key(live.current.configuration, live.current.historyKey) !== synced.current) {
      throw new Error('草稿尚未同步，请完成同步后检查。');
    }
    running.current = true;
    rejectedProjection.current = undefined;
    dispatchSync({ type: 'start', creating: !remote.current });
    const beforeKey = key(live.current.configuration, live.current.historyKey);
    pendingKey.current = beforeKey;
    let workspace: Workspace | undefined;
    let request: Record<string, unknown> | undefined;
    pending.current = async () => {
      workspace ??= await ensure();
      request ??= {
        draft_id: workspace.id,
        expected_revision: workspace.revision,
        operation_id: crypto.randomUUID(),
        refresh_knowledge: refreshKnowledge,
        upgrade_calculation: false,
        upgrade_decisions: false,
      };
      checkpoints.current.set(beforeKey, workspace.revision);
      return mergeDelta(workspace, await post<Delta>(`/work-drafts/${workspace.id}/check`, request));
    };
    try {
      const result = await pending.current();
      remote.current = result;
      pending.current = undefined;
      pendingKey.current = undefined;
      checkpoints.current.set(key(result.configuration, live.current.historyKey), result.revision);
      synced.current = key(result.configuration, live.current.historyKey);
      if (key(live.current.configuration, live.current.historyKey) !== beforeKey) {
        throw new Error('检查期间本地已变化，检查结果已保存但未覆盖本地编辑，请恢复草稿核对。');
      }
      live.current.accept(result.checked);
      dispatchSync({ type: 'success' });
      return result.checked;
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 422 || cause.status === 409)) {
        pending.current = undefined;
        pendingKey.current = undefined;
      }
      dispatchSync({ type: 'failure', error: cause instanceof Error ? cause.message : String(cause),
        conflict: cause instanceof ApiError && cause.status === 409 });
      throw cause;
    } finally {
      running.current = false;
      render((value) => value + 1);
    }
  };
  const acceptCheckpoint = (workspace: Workspace) => {
    const historyKey = `workspace:${workspace.id}:${workspace.revision}`;
    synced.current = key(workspace.configuration, historyKey);
    checkpoints.current.set(synced.current, workspace.revision);
    live.current.acceptCheckpoint?.(workspace.checked, historyKey);
  };
  const canDiscardRejected = Boolean(remote.current && !running.current && !pending.current &&
    rejectedProjection.current === currentKey && currentKey !== synced.current);
  const discardRejected = () => {
    const workspace = remote.current;
    if (!workspace || running.current || pending.current || rejectedProjection.current !== key(live.current.configuration, live.current.historyKey)) {
      throw new Error('仅可撤回服务端明确未通过校验、且之后没有继续修改的本地内容。');
    }
    // The server rejected this exact projection; an uncertain response must keep its retry.
    rejectedProjection.current = undefined;
    synced.current = key(workspace.configuration, live.current.historyKey);
    live.current.accept(workspace.checked);
    dispatchSync({ type: 'success' });
  };
  return { phase, syncing, unsynced, error, retry: synchronize, canDiscardRejected, discardRejected,
    preview, save, readyWorkspace, execute: (operations: Operation[]) => executeWrite(operations),
    recheck: (input: RecheckInput) => executeWrite([], input), check,
    id: remote.current?.id, revision: remote.current?.revision };
}
