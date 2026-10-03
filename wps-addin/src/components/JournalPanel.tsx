import { useState } from 'react';
import { restoreJournal } from '../editJournal';
import type { HostAdapter } from '../host';
import type { WorkbookMetadata } from '../types';
import { captureWorkbookSession, inWorkbookSession } from '../workbookSession';

export function JournalPanel({ host, onChanged }: {
  host: HostAdapter; onChanged: (metadata: WorkbookMetadata) => void;
}) {
  const [error, setError] = useState('');
  const [session] = useState(() => captureWorkbookSession(host));
  const journals = host.journals();
  const pending = journals.filter((j) => j.state === 'prepared' || j.state === 'recovery_required');
  const latest = journals.filter((j) => j.state === 'applied').at(-1);
  const restore = (journal: typeof journals[number], undo: boolean) => {
    setError('');
    try { onChanged(inWorkbookSession(host, { session, run: () => restoreJournal(host, journal, undo) })); }
    catch (reason) { setError(String(reason)); }
  };
  return <section aria-label="插件撤销与恢复">
    {pending.map((journal) => <div className="error" key={journal.operation_id}>
      <p>有未完成的工作簿操作：{journal.error ?? journal.operation_id}</p>
      <button onClick={() => restore(journal, false)}>检查并恢复本组修改</button>
    </div>)}
    <button disabled={!latest || pending.length > 0} onClick={() => latest && restore(latest, true)}>撤销本次补全</button>
    {error && <div className="error" role="alert">{error}</div>}
  </section>;
}
