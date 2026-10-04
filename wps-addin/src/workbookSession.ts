import type { ActiveCell, InlineEditorContext, WorkbookMetadata } from './types';
import { isProductInputCell } from './productInput.ts';

interface SessionHost {
  workbookKey(): string;
  readMetadata(): WorkbookMetadata;
}

interface InlineSessionHost extends SessionHost {
  inlineContext(): Pick<InlineEditorContext, 'session_id'> | null;
}

export function captureWorkbookSession(host: SessionHost) {
  return { workbookKey: host.workbookKey(), bindingId: host.readMetadata().binding?.binding_id };
}

export function isWorkbookSession(host: SessionHost, session: ReturnType<typeof captureWorkbookSession>) {
  return host.workbookKey() === session.workbookKey
    && host.readMetadata().binding?.binding_id === session.bindingId;
}

export function assertWorkbookSession(host: SessionHost, session: ReturnType<typeof captureWorkbookSession>) {
  if (!isWorkbookSession(host, session)) {
    throw new Error('工作簿或项目绑定已切换，未写入当前文件；请返回原工作簿重试或恢复同步回执');
  }
}

export function assertInlineSession(host: InlineSessionHost, context: InlineEditorContext) {
  if (!context.workbook_key) throw new Error('单元格上下文缺少文件身份，请重新选择单元格');
  assertWorkbookSession(host, { workbookKey: context.workbook_key, bindingId: context.binding_id });
  if (!context.session_id || host.inlineContext()?.session_id !== context.session_id) {
    throw new Error('补全单元格已切换，未采用旧结果或写入旧输入；请在当前单元格重新查询');
  }
}

export function writeInlineInput(options: {
  host: InlineSessionHost & { writeCellValue(cell: ActiveCell, value: string): void };
  context: InlineEditorContext; value: string;
}) {
  assertInlineSession(options.host, options.context);
  if (!isProductInputCell(options.context.profile, options.context.cell)) {
    throw new Error('请选择表头下方、由插件管理的型号、名称或说明单元格');
  }
  options.host.writeCellValue(options.context.cell, options.value);
}

export function inWorkbookSession<T>(host: SessionHost, options: {
  session?: ReturnType<typeof captureWorkbookSession>; run: () => T;
}): T {
  if (!options.session) throw new Error('候选上下文已失效，请重新输入');
  assertWorkbookSession(host, options.session);
  return options.run();
}
