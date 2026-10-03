import type { nextEditNotice } from '../nextEditPresentation';

export function NextEditNotice({ notice }: { notice: ReturnType<typeof nextEditNotice> }) {
  if (!notice) return null;
  return <div className="inline-status inline-next-notice" aria-label="下一处修改提示">
    <div title={notice.target}>{notice.target}</div>
    <div title={notice.reason}>理由：{notice.reason}</div>
    <div title={notice.action}>{notice.action}</div>
  </div>;
}
