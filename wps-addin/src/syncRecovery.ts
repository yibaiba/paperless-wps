import type { BindingState, WorkbookLine, WorkbookMetadata } from './types';

export function recoverSyncReceipt(metadata: WorkbookMetadata, result: BindingState): WorkbookMetadata {
  const pending = metadata.pending_sync;
  if (!pending) throw new Error('本地同步回执请求缺失，不能覆盖工作簿绑定');
  if (result.binding_id !== metadata.binding?.binding_id) throw new Error('同步回执属于其他工作簿绑定');
  const operations = metadata.business?.operations ?? [];
  if (JSON.stringify(operations.slice(0, pending.operations.length)) !== JSON.stringify(pending.operations)) {
    throw new Error('同步期间业务操作已被撤销或重排，请保留回执并处理冲突');
  }
  const local = new Map(metadata.line_bindings.map((line) => [line.line_id, line]));
  const removed = new Set(((pending.request?.removed_lines ?? []) as WorkbookLine[]).map((line) => line.line_id));
  const lines = metadata.line_bindings.filter((line) => !removed.has(line.line_id)).map((line) => {
    const synced = result.line_bindings.find((b) => b.line_id === line.line_id);
    return synced ? { ...line, device_id: synced.device_id, content_fingerprint: synced.content_fingerprint } : line;
  });
  for (const line of result.line_bindings) {
    if (!local.has(line.line_id)) lines.push({ ...pending.line_bindings.find((b) => b.line_id === line.line_id), ...line });
  }
  return { ...metadata, binding: result, line_bindings: lines, pending_sync: undefined,
    business: metadata.business ? { ...metadata.business,
      operations: operations.slice(pending.operations.length), local_revision: metadata.business.local_revision + 1,
      removed_lines: metadata.business.removed_lines?.filter((line) => !removed.has(line.line_id)),
    } : undefined,
  };
}
