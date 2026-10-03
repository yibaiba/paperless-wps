import type { ActiveCell, InlineEditorContext, WorkbookMetadata } from './types';

interface SessionHost {
  workbookKey(): string;
  readMetadata(): WorkbookMetadata;
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

export function assertInlineSession(host: SessionHost, context: InlineEditorContext) {
  if (!context.workbook_key) throw new Error('单元格上下文缺少文件身份，请重新选择单元格');
  assertWorkbookSession(host, { workbookKey: context.workbook_key, bindingId: context.binding_id });
}

export function writeInlineInput(options: {
  host: SessionHost & { writeCellValue(cell: ActiveCell, value: string): void };
  context: InlineEditorContext; value: string;
}) {
  assertInlineSession(options.host, options.context);
  options.host.writeCellValue(options.context.cell, options.value);
}

export function inWorkbookSession<T>(host: SessionHost, options: {
  session?: ReturnType<typeof captureWorkbookSession>; run: () => T;
}): T {
  if (!options.session) throw new Error('候选上下文已失效，请重新输入');
  assertWorkbookSession(host, options.session);
  return options.run();
}
