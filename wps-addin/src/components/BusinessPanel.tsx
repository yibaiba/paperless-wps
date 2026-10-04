import { useEffect, useMemo, useState } from 'react';
import type { WpsApi } from '../api';
import type { CompletionPreviewResult, WorkbookBusinessContext } from '../businessTypes';
import { completionRequest } from '../businessWorkbook';
import { recentHistoryKey } from '../recentBusinessEdits';
import { applyNextEdit } from '../editJournal';
import type { HostAdapter } from '../host';
import type { TemplateProfile, WorkbookMetadata } from '../types';
import { WorkbookRowIndex } from '../workbookRowIndex';
import { BusinessSettings } from './BusinessSettings';
import { JournalPanel } from './JournalPanel';
import { NextEditPreview, issueText } from './NextEditPreview';
import { BusinessRowPanel } from './BusinessRowPanel';
import { BusinessContextDetails, KnowledgeDetails } from './BusinessContextDetails';
import { completionMode, decisionText } from '../businessContextPresentation';
import { assertWorkbookSession, captureWorkbookSession, inWorkbookSession } from '../workbookSession';

export function BusinessPanel({ api, host, profile, metadata, onChanged }: {
  api: WpsApi; host: HostAdapter; profile: TemplateProfile; metadata: WorkbookMetadata;
  onChanged: (value: WorkbookMetadata) => void;
}) {
  const [context, setContext] = useState<WorkbookBusinessContext>();
  const [result, setResult] = useState<CompletionPreviewResult>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [session] = useState(() => captureWorkbookSession(host));
  const index = useMemo(() => new WorkbookRowIndex(host, profile), [host, profile]);
  useEffect(() => host.onSheetChange((event) => {
    setResult(undefined);
    try { index.changed(event, { historyKey: recentHistoryKey(host.readMetadata()) }); }
    catch (reason) { setError(`读取变更行失败：${reason}`); }
  }), [host, index]);
  useEffect(() => { setResult(undefined); }, [metadata]);
  useEffect(() => {
    let current = true;
    setResult(undefined); setContext(undefined); setError('');
    if (metadata.binding) api.businessContext(metadata.binding.binding_id).then((value) => {
      if (current) setContext(value);
    }).catch((reason) => { if (current) setError(String(reason)); });
    return () => { current = false; };
  }, [api, metadata.binding?.binding_id, metadata.binding?.binding_revision, metadata.binding?.draft_revision]);

  async function preview(intent: 'next' | 'remove' = 'next') {
    setBusy(true); setError(''); setResult(undefined);
    try {
      assertWorkbookSession(host, session);
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
    <p>当前模式：{completionMode(metadata.schema_version)}</p>
    {metadata.schema_version !== 2 && <p>在下方确认业务区与固定系统版本后，升级为业务上下文推荐；保留原绑定和产品身份。</p>}
    <p>项目：{metadata.binding?.project_id ?? '未绑定'} · 基线 v{metadata.binding?.base_revision ?? '未绑定'}</p>
    <p>目录：{profile.catalog_scope ? `${profile.catalog_scope.sheet} · ${profile.catalog_scope.import_id}` : '来源范围尚未确认'}</p>
    {currentContext && metadata.business?.scopes.map((scope) => <p key={`${scope.sheet}:${scope.start_row}`}>
      {scope.sheet} {scope.start_row}–{scope.end_row} 行 · {currentContext.configuration.rooms.find((r) => r.id === scope.room_id)?.name ?? '房间未确认'} / {currentContext.configuration.systems.find((s) => s.id === scope.system_id)?.name ?? scope.system_id}
    </p>)}
    {context?.knowledge_summary && <KnowledgeDetails items={context.knowledge_summary} />}
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
    {result && <><p role="status">{decisionText(result.decision)}</p><BusinessContextDetails summary={result.context_summary} /></>}
    {result?.items.map((item) => <NextEditPreview key={item.id} suggestion={item} contextSummary={result.context_summary} onApply={() => {
      try {
        const next = inWorkbookSession(host, { session,
          run: () => applyNextEdit({ host, suggestion: item, operationId: crypto.randomUUID() }) });
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
