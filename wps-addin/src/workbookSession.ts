import type { WorkbookMetadata } from './types';

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
