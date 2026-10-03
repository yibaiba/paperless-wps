import { useEffect, useMemo, useState } from 'react';
import type { WpsApi } from '../api';
import type { CompletionPreviewResult, WorkbookBusinessContext } from '../businessTypes';
import { completionRequest } from '../businessWorkbook';
import { applyNextEdit } from '../editJournal';
import type { HostAdapter } from '../host';
import type { TemplateProfile, WorkbookMetadata } from '../types';
import { WorkbookRowIndex } from '../workbookRowIndex';
import { BusinessSettings } from './BusinessSettings';
import { JournalPanel } from './JournalPanel';
import { NextEditPreview, issueText } from './NextEditPreview';
import { BusinessRowPanel } from './BusinessRowPanel';
import { assertWorkbookSession, captureWorkbookSession } from '../workbookSession';

export function BusinessPanel({ api, host, profile, metadata, onChanged }: {
  api: WpsApi; host: HostAdapter; profile: TemplateProfile; metadata: WorkbookMetadata;
  onChanged: (value: WorkbookMetadata) => void;
}) {
  const [context, setContext] = useState<WorkbookBusinessContext>();
  const [result, setResult] = useState<CompletionPreviewResult>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const index = useMemo(() => new WorkbookRowIndex(host, profile), [host, profile]);
  useEffect(() => host.onSheetChange((event) => { index.changed(event); setResult(undefined); }), [host, index]);
  useEffect(() => { setResult(undefined); }, [metadata]);
  useEffect(() => {
    let current = true;
    setResult(undefined);
    if (metadata.binding) api.businessContext(metadata.binding.binding_id).then((value) => {
      if (current) setContext(value);
    }).catch((reason) => { if (current) setError(String(reason)); });
    return () => { current = false; };
  }, [api, metadata.binding]);

  async function preview(intent: 'next' | 'remove' = 'next') {
    setBusy(true); setError(''); setResult(undefined);
    try {
      const session = captureWorkbookSession(host);
      const cell = host.activeCell();
      const value = await api.completionPreview({ ...completionRequest({ host, profile,
        metadata: host.readMetadata(), cell, index, query: '' }), intent });
      assertWorkbookSession(host, session);
      if (value.local_revision !== host.businessRevision()) throw new Error('工作簿在计算时发生变化，请重新预览');
      setResult(value);
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }

  const currentContext = context && { ...context, configuration: result?.configuration ?? localSettings(context, metadata) };
  return <section className="panel-section" aria-label="下一步业务编辑">
    <h2>下一步业务编辑</h2>
    {!metadata.binding && <p>先绑定项目，再确认业务区。旧版基本补全继续保留。</p>}
    {context && <BusinessSettings context={currentContext!} host={host} metadata={metadata} profile={profile} onSaved={onChanged} />}
    {metadata.business && context && <>
      <BusinessRowPanel api={api} host={host} profile={profile} metadata={metadata} context={currentContext!} onChanged={onChanged} />
      <JournalPanel host={host} onChanged={(value) => { setResult(undefined); onChanged(value); }} />
      <button disabled={busy} onClick={() => preview()}>{busy ? '计算受影响的需求…' : '预览当前业务区下一步'}</button>
      <button disabled={busy} onClick={() => preview('remove')}>预览移除当前产品（不删工作表行）</button>
    </>}
    {error && <div className="error" role="alert">{error}</div>}
    {result?.issues.map((issue, i) => <div className="issue" key={i}>{issueText(issue)}</div>)}
    {result && !result.items.length && <p>当前没有可应用的下一步。请处理上方待确认项；需求已满足时不会继续推荐采购。</p>}
    {result?.items.map((item) => <NextEditPreview key={item.id} suggestion={item} onApply={() => {
      try {
        const next = applyNextEdit({ host, suggestion: item, operationId: crypto.randomUUID() });
        onChanged(next); setResult(undefined);
      } catch (reason) { setError(String(reason)); }
    }} />)}
  </section>;
}

function localSettings(context: WorkbookBusinessContext, metadata: WorkbookMetadata) {
  const configuration = { ...context.configuration, rooms: [...context.configuration.rooms],
    systems: [...context.configuration.systems], requirements: [...context.configuration.requirements] };
  // Display explicitly saved settings before the next server projection, without calculating rules.
  for (const operation of metadata.business?.operations ?? []) {
    if (operation.action === 'system_setup') {
      const system = operation.system as typeof configuration.systems[number];
      configuration.systems = [...configuration.systems.filter((s) => s.id !== system.id), system];
      if (operation.new_room) configuration.rooms.push(operation.new_room as typeof configuration.rooms[number]);
      if (operation.room_inputs && system.room_id) configuration.room_inputs = {
        ...configuration.room_inputs, [system.room_id]: operation.room_inputs as NonNullable<typeof configuration.room_inputs>[string],
      };
      if (operation.project_inputs) configuration.project_inputs = operation.project_inputs as typeof configuration.project_inputs;
    }
    if (operation.action === 'requirement_put') {
      const value = operation.value as typeof configuration.requirements[number];
      configuration.requirements = [...configuration.requirements.filter((r) => r.id !== value.id), value];
    }
  }
  return configuration;
}
