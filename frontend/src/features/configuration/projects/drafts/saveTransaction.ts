import type { ProjectConfiguration } from '../../types';
import type { Workspace } from './transport';

interface CheckReceipt { revision: number; check_fingerprint: string }
interface SaveReceipt { revision: number; project_revision: number }
interface Dependencies {
  post: <T>(path: string, value: unknown) => Promise<T>;
  readWorkspace: (id: string) => Promise<Workspace>;
  readProject: () => Promise<ProjectConfiguration>;
  acceptWorkspace: (workspace: Workspace) => void;
  newId: () => string;
  isRejected: (cause: unknown) => boolean;
}
interface Attempt {
  workspace: Workspace; checkId: string; saveId: string;
  checked?: CheckReceipt; saved?: SaveReceipt; refreshed?: Workspace; rejection?: unknown;
}

// Keep acknowledged phases and request IDs until an uncertain write is resolved.
// Reading the result is separate from committing, so a failed read cannot replay an old save over a new edit.
export function createSaveTransaction(io: Dependencies) {
  let pending: Attempt | undefined;
  let settling: Promise<void> | undefined;
  const commit = async () => {
    const attempt = pending;
    if (!attempt || attempt.refreshed) return;
    const workspace = attempt.workspace;
    try {
      if (!attempt.rejection) {
        attempt.checked ??= await io.post<CheckReceipt>('/list-tools/list_check', {
          draft_id: workspace.id, expected_revision: workspace.revision, operation_id: attempt.checkId,
        });
        attempt.saved ??= await io.post<SaveReceipt>('/list-tools/list_save', {
          draft_id: workspace.id, expected_revision: attempt.checked.revision, operation_id: attempt.saveId,
          expected_project_revision: workspace.base_revision, fingerprint: attempt.checked.check_fingerprint,
        });
      }
    } catch (cause) {
      if (!io.isRejected(cause)) throw cause;
      attempt.rejection = cause;
    }
    attempt.refreshed = await io.readWorkspace(workspace.id);
    io.acceptWorkspace(attempt.refreshed);
    if (attempt.rejection) { pending = undefined; throw attempt.rejection; }
  };
  const settle = () => settling ??= commit().finally(() => { settling = undefined; });
  const save = async (workspace: Workspace) => {
    if (!pending || (pending.refreshed && pending.refreshed.revision !== workspace.revision)) {
      pending = { workspace, checkId: io.newId(), saveId: io.newId() };
    }
    await settle();
    const attempt = pending;
    const result = await io.readProject();
    if (result.revision !== attempt.saved!.project_revision) {
      throw new Error('项目已有其他保存版本，本次返回未覆盖草稿，请核对项目版本。');
    }
    pending = undefined;
    return result;
  };
  return { settle, save };
}
