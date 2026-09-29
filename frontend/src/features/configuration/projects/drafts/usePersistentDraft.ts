import { useEffect, useRef, useState } from 'react';
import { useBlocker, useSearchParams } from 'react-router-dom';
import { App } from 'antd';
import { api, ApiError } from '../../../../shared/api';
import type { Checked, Configuration, ProjectConfiguration } from '../../types';
import type { EditPreview } from '../../quotation/sheet/useSheetEditing';
import type { EditOperation } from '../../quotation/sheet/model';
import { type Operation, configurationOperations } from './operations';
import { mergeDelta, post, writeRequest, type Delta, type Workspace } from './transport';

const key = (config: Configuration) => JSON.stringify(config);
interface Options {
  projectId: string; saved: ProjectConfiguration; configuration: Configuration;
  initialWorkspace?: Workspace; accept: (checked: Checked) => void; acceptOperation: (checked: Checked) => void;
}
export function usePersistentDraft(options: Options) {
  const live = useRef(options); live.current = options;
  const [, setParams] = useSearchParams();
  const remote = useRef<Workspace | undefined>(options.initialWorkspace);
  const synced = useRef(key(options.initialWorkspace?.configuration ?? options.saved.configuration));
  const checkpoints = useRef(new Map<string, number>(options.initialWorkspace ? [[key(options.initialWorkspace.configuration), options.initialWorkspace.revision]] : []));
  const pending = useRef<(() => Promise<Workspace>) | undefined>(undefined);
  const operationPending = useRef(false);
  const pendingKey = useRef<string | undefined>(undefined);
  const creating = useRef<Promise<Workspace> | undefined>(undefined);
  const running = useRef(false), alive = useRef(true);
  const [error, setError] = useState(''), [syncing, setSyncing] = useState(false);
  const [, render] = useState(0);
  const { modal } = App.useApp();
  const creationId = useRef(crypto.randomUUID());
  const currentKey = key(options.configuration);
  const unsynced = currentKey !== synced.current;
  const ensure = async () => {
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
    running.current = true; setSyncing(true); setError('');
    const target = live.current.configuration, targetKey = key(target);
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
            if (targetKey !== key(workspace.configuration)) throw new Error("草稿包含未转换为业务操作的变化，尚未同步；请保留页面并核对。");
            synced.current = targetKey; return;
          }
          const request = writeRequest(workspace, operations);
          pending.current = async () => mergeDelta(workspace, await post<Delta>(`/work-drafts/${workspace.id}/edit`, request));
        }
      }
      const result = await pending.current();
      const appliedKey = pendingKey.current!;
      const wasOperation = operationPending.current; operationPending.current = false;
      pending.current = undefined; pendingKey.current = undefined; remote.current = result;
      if (!wasOperation) checkpoints.current.set(appliedKey, result.revision);
      checkpoints.current.set(key(result.configuration), result.revision);
      synced.current = appliedKey;
      if (alive.current && key(live.current.configuration) === appliedKey) {
        synced.current = key(result.configuration);
        if (wasOperation) live.current.acceptOperation(result.checked); else live.current.accept(result.checked);
      }
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 422 || cause.status === 409)) { pending.current = undefined; pendingKey.current = undefined; operationPending.current = false; }
      if (alive.current) setError(cause instanceof Error ? cause.message : String(cause));
    }
    finally { running.current = false; if (alive.current) { setSyncing(false); render((v) => v + 1); } }
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
    if (running.current || pending.current || key(live.current.configuration) !== synced.current) throw new Error('草稿尚未同步，请先完成同步或重试。');
    const workspace = await ensure();
    const result = await post<Delta & { draft_version: number }>(`/work-drafts/${workspace.id}/preview`, { expected_revision: workspace.revision, draft_version: version, operations });
    return { draft_version: result.draft_version, checked: mergeDelta(workspace, { ...result, revision: workspace.revision }).checked, changes: [] } as EditPreview;
  };
  const savePending = useRef<(() => Promise<ProjectConfiguration>) | undefined>(undefined);
  const save = async () => {
    if (running.current || pending.current || key(live.current.configuration) !== synced.current) throw new Error('草稿尚未同步，请先重试同步。');
    const workspace = await ensure();
    if (!savePending.current) {
      const checkRequest = { draft_id: workspace.id, expected_revision: workspace.revision, operation_id: crypto.randomUUID() };
      const saveId = crypto.randomUUID();
      savePending.current = async () => {
        const checked = await post<{ revision: number; check_fingerprint: string }>('/list-tools/list_check', checkRequest);
        await post('/list-tools/list_save', { draft_id: workspace.id, expected_revision: checked.revision,
          operation_id: saveId, expected_project_revision: workspace.base_revision, fingerprint: checked.check_fingerprint });
        remote.current = await api<Workspace>('/work-drafts/' + workspace.id);
        return api<ProjectConfiguration>('/configuration/projects/' + live.current.projectId);
      };
    }
    const result = await savePending.current();
    savePending.current = undefined;
    return result;
  };
  const readyWorkspace = async () => {
    if (running.current || pending.current || key(live.current.configuration) !== synced.current) throw new Error('草稿尚未同步，请完成同步后生成方案。');
    return ensure();
  };
  const execute = async (operations: Operation[]) => {
    const workspace = await readyWorkspace();
    running.current = true; setSyncing(true); setError('');
    const beforeKey = key(live.current.configuration);
    const request = writeRequest(workspace, operations);
    pendingKey.current = beforeKey; operationPending.current = true;
    checkpoints.current.set(beforeKey, workspace.revision);
    pending.current = async () => mergeDelta(workspace, await post<Delta>(`/work-drafts/${workspace.id}/edit`, request));
    try {
      const result = await pending.current();
      remote.current = result; pending.current = undefined; pendingKey.current = undefined; operationPending.current = false;
      checkpoints.current.set(beforeKey, workspace.revision);
      checkpoints.current.set(key(result.configuration), result.revision);
      synced.current = key(result.configuration);
      if (key(live.current.configuration) !== beforeKey) throw new Error('采用期间本地已变化，提案已同步但未覆盖本地编辑，请恢复草稿核对。');
      return result.checked;
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 422 || cause.status === 409)) { pending.current = undefined; pendingKey.current = undefined; operationPending.current = false; }
      setError(cause instanceof Error ? cause.message : String(cause)); throw cause;
    } finally { running.current = false; setSyncing(false); render(v => v + 1); }
  };
  return { syncing, unsynced, error, retry: synchronize, preview, save, readyWorkspace, execute, id: remote.current?.id };
}
