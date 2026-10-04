import type { CompletionPreviewResult, NextEditSuggestion, WorkbookEditJournal } from './businessTypes';
import type { HostAdapter } from './host';
import type { InlineEditorContext, WorkbookMetadata } from './types';
import type { RequestAttempt } from './latestRequest';
import { applyNextEdit, restoreJournal, type JournalHost } from './editJournal.ts';
import { assertInlineSession, assertWorkbookSession, captureWorkbookSession } from './workbookSession.ts';

export class AppliedCompletionRefreshError extends Error {
  constructor(cause: unknown) {
    super(`本组修改已写入，但下一步刷新失败：${String(cause)}`, { cause });
  }
}

export function applyBusinessCompletion(options: {
  host: JournalHost; suggestion: NextEditSuggestion; operationId: string;
  afterApply: (metadata: WorkbookMetadata) => void;
}) {
  const metadata = applyNextEdit(options);
  // A refresh failure cannot turn a durable, successful journal into a failed write.
  try { options.afterApply(metadata); }
  catch (reason) { throw new AppliedCompletionRefreshError(reason); }
}

export class UndoneCompletionRefreshError extends Error {
  constructor(cause: unknown) {
    super(`本组修改已撤销，但补全刷新失败：${String(cause)}`, { cause });
  }
}

export function undoBusinessCompletion(options: {
  host: JournalHost; journal: WorkbookEditJournal; afterUndo: (metadata: WorkbookMetadata) => void;
}) {
  const metadata = restoreJournal(options.host, options.journal);
  try { options.afterUndo(metadata); }
  catch (reason) { throw new UndoneCompletionRefreshError(reason); }
}

export async function resolveBusinessChoice(options: {
  host: Pick<HostAdapter, 'workbookKey' | 'readMetadata' | 'businessRevision' | 'inlineContext'>;
  context: InlineEditorContext; request: RequestAttempt;
  load: (signal: AbortSignal) => Promise<CompletionPreviewResult>;
}) {
  const { host, context, request, load } = options;
  assertInlineSession(host, context);
  const session = captureWorkbookSession(host);
  const result = await load(request.signal);
  if (!request.isCurrent()) return undefined;
  assertWorkbookSession(host, session);
  if (host.inlineContext()?.session_id !== context.session_id) throw new Error('补全单元格已切换，未应用旧选择');
  if (result.local_revision !== host.businessRevision()) throw new Error('选择期间工作簿已变化，请重新查询');
  return result;
}
