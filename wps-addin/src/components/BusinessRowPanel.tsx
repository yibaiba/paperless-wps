import { useEffect, useRef, useState } from 'react';
import type { WpsApi } from '../api';
import type { NextEditSuggestion, ProductKind, ResolutionAction, WorkbookBusinessContext } from '../businessTypes';
import { rowBusinessOperations } from '../businessRowOperations';
import { assertWorkbookSession, captureWorkbookSession, inWorkbookSession } from '../workbookSession';
import { applyNextEdit } from '../editJournal';
import { deviceIdForLine } from '../businessIdentity';
import type { HostAdapter } from '../host';
import type { Candidate, TemplateProfile, WorkbookMetadata } from '../types';
import { businessSyncRequest } from '../businessWorkbook';
import { scanWorkbook } from '../workbook';
import { NextEditPreview } from './NextEditPreview';

export function BusinessRowPanel({ api, host, profile, metadata, context, onChanged, resolution }: {
  api: WpsApi; host: HostAdapter; profile: TemplateProfile; metadata: WorkbookMetadata;
  context: WorkbookBusinessContext; onChanged: (value: WorkbookMetadata) => void;
  resolution?: ResolutionAction;
}) {
  const [cell, setCell] = useState(() => host.activeCell());
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState('');
  const [kind, setKind] = useState<ProductKind | ''>('');
  const [role, setRole] = useState('');
  const [deviceId, setDeviceId] = useState('');
  const [supply, setSupply] = useState('');
  const [evidence, setEvidence] = useState('');
  const [environmentKey, setEnvironmentKey] = useState('');
  const [environmentValue, setEnvironmentValue] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<NextEditSuggestion>();
  const [session] = useState(() => captureWorkbookSession(host));
  const panel = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (resolution?.kind !== 'confirm_identity') return;
    setCell(host.activeCell()); setPreview(undefined); setSelected(''); setCandidates([]);
    if (panel.current) { panel.current.open = true; panel.current.focus(); }
  }, [host, resolution]);
  useEffect(() => host.onSelectionChange(() => {
    setCell(host.activeCell()); setCandidates([]); setSelected(''); setKind(''); setRole('');
    setDeviceId(''); setSupply(''); setPreview(undefined);
  }), [host]);
  const scope = metadata.business?.scopes.find((s) => s.sheet === cell.sheet && s.start_row <= cell.row && s.end_row >= cell.row);
  const system = context.configuration.systems.find((s) => s.id === scope?.system_id);
  const pkg = context.definitions.packages.find((p) => p.id === system?.knowledge_package_id);
  const old = metadata.line_bindings.find((b) => b.sheet === cell.sheet && b.row === cell.row);
  const candidate = candidates.find((c) => c.key === selected);

  async function identify() {
    setBusy(true); setError('');
    try {
      assertWorkbookSession(host, session);
      const row = host.readRow(profile, cell.row);
      const result = await api.suggestions({ query: row.values.model || row.values.name || '',
        template_profile_id: profile.id, template_profile_revision: profile.revision,
        current_row: row.values });
      assertWorkbookSession(host, session);
      const active = host.activeCell();
      if (active.sheet !== cell.sheet || active.row !== cell.row) throw new Error('选区已变化，请重新解析当前行');
      setCandidates(result.items); setSelected('');
      if (!result.items.length) setError('没有可确认的产品身份，请核对名称或型号');
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }

  async function confirm() {
    setError(''); setBusy(true); setPreview(undefined);
    try {
      assertWorkbookSession(host, session);
      const revision = host.businessRevision();
      if (!metadata.business || !scope || !system) throw new Error('先明确当前行所在业务区');
      const row = host.readRow(profile, cell.row);
      const product = candidate ?? old;
      const productKind = kind || old?.kind;
      const hasProduct = Boolean(row.values.model || row.values.name);
      if (hasProduct && (!product || !productKind)) throw new Error('请选择具体配置、来源和真实产品类型');
      if (old && product && (old.variant_id !== product.variant_id || old.source_id !== product.source_id)) {
        throw new Error('已确认行换型请使用单元格补全与差异预览，以同时处理失效价格和关联');
      }
      const chosenRole = pkg?.definition.roles.find((r) => r.id === role);
      const requirementId = old?.requirement_id ?? crypto.randomUUID();
      const lineId = old?.line_id ?? crypto.randomUUID();
      const linkedDevice = deviceId || old?.device_id || (hasProduct
        ? await deviceIdForLine(metadata.binding!.binding_id, lineId) : undefined);
      assertWorkbookSession(host, session);
      const existingDevice = context.configuration.devices.find((d) => d.id === linkedDevice);
      if (existingDevice && product && (existingDevice.variant_id !== product.variant_id || existingDevice.source_id !== product.source_id)) {
        throw new Error('已有设备配置/来源与当前行不同，请选择一致身份；换型请走下一步预览');
      }
      const binding = hasProduct && product && productKind ? { ...old, line_id: lineId,
        sheet: cell.sheet, row: cell.row, variant_id: product.variant_id, source_id: product.source_id,
        kind: productKind, device_id: linkedDevice, requirement_id: chosenRole ? requirementId : old?.requirement_id,
        confirmed_values: row.values, anchor_fingerprint: [row.values.model ?? '', row.values.name ?? ''].join('\0').toLocaleLowerCase(),
      } : undefined;
      const proposed = { ...metadata, line_bindings: [
        ...metadata.line_bindings.filter((line) => line.line_id !== lineId), ...(binding ? [binding] : []),
      ], business: { ...metadata.business,
        unresolved_line_ids: metadata.business.unresolved_line_ids?.filter((id) => id !== lineId) } };
      let configuration = context.configuration;
      if (chosenRole || supply) {
        const scan = scanWorkbook(host.readRows(profile), proposed);
        if (scan.unresolved.length) throw new Error(`${scan.unresolved.join('；')}。可先仅确认产品身份，再设置用途与供货。`);
        const before = await api.preview(businessSyncRequest(proposed, scan.lines));
        assertWorkbookSession(host, session);
        if (!before.configuration) throw new Error('后端未返回当前业务配置，请升级后端后重试');
        configuration = before.configuration;
      }
      const { operations, inverse } = rowBusinessOperations({ configuration, requirementId,
        systemId: system.id, deviceId: linkedDevice, role: chosenRole, environmentKey, environmentValue,
        supply, quantity: row.values.quantity ?? '', evidence, allocationId: crypto.randomUUID() });
      const active = host.activeCell();
      if (active.sheet !== cell.sheet || active.row !== cell.row) throw new Error('选区已变化，请重新确认当前行');
      const suggestion: NextEditSuggestion = {
        id: crypto.randomUUID(), kind: 'identity', label: '人工确认当前行身份与用途', patches: [],
        line_bindings: binding ? [binding] : [], business_operations: operations, inverse_business_operations: inverse,
        confirmed_identity_ids: [lineId],
        row_requirements: !hasProduct && chosenRole
          ? [...(metadata.business.row_requirements ?? []).filter((r) => r.sheet !== cell.sheet || r.row !== cell.row),
            { sheet: cell.sheet, row: cell.row, requirement_id: requirementId }] : undefined,
        changes: [{ kind: '产品身份', id: lineId, before: old, after: binding }],
        evidence: [{ source: '人工明确选择', kind: productKind, supply, evidence }], issues: [], applicable: true, acceptance: 'preview',
        context_fingerprint: context.fingerprint, local_revision: revision,
      };
      if (operations.length) {
        const after = { ...proposed, business: { ...proposed.business,
          operations: [...proposed.business.operations, ...operations] } };
        const scan = scanWorkbook(host.readRows(profile), after);
        if (scan.unresolved.length) throw new Error(`${scan.unresolved.join('；')}。可先仅确认产品身份，再设置用途与供货。`);
        const checked = await api.preview(businessSyncRequest(after, scan.lines));
        assertWorkbookSession(host, session);
        suggestion.changes.push(...checked.changes);
        suggestion.issues = checked.issues;
        suggestion.applicable = !checked.issues.some((issue) => typeof issue === 'object' && issue !== null
          && 'status' in issue && issue.status === 'conflict');
      }
      if (host.businessRevision() !== revision) throw new Error('预览期间工作簿已变化，请重新确认');
      setPreview(suggestion);
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }

  return <details ref={panel} tabIndex={-1}><summary>确认当前行产品 / 用途：{cell.sheet} · {cell.row}</summary>
    <p>手填旧行不会自动绑定。重复型号、多个来源均须明确选择。</p>
    <button onClick={identify} disabled={busy}>解析当前行产品身份</button>
    <label>配置与来源<select value={selected} onChange={(e) => setSelected(e.target.value)}><option value="">{old ? '保留已确认产品' : '请选择'}</option>
      {candidates.map((c) => <option key={c.key} value={c.key}>{c.model} · {c.variant_name} · {c.source.sheet}:{c.source.row}</option>)}</select></label>
    <label>真实产品类型<select value={kind || old?.kind || ''} onChange={(e) => setKind(e.target.value as ProductKind)}><option value="">请选择</option>
      <option value="hardware">硬件</option><option value="software">软件</option><option value="license">授权</option><option value="accessory">配套</option></select></label>
    <label>已有项目设备<select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}><option value="">{old?.device_id ? '保留原设备身份' : '新产品行'}</option>
      {context.configuration.devices.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.id}</option>)}</select></label>
    <label>当前行用途<select value={role} onChange={(e) => setRole(e.target.value)}><option value="">保留 / 尚未确认</option>
      {pkg?.definition.roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
    {role && <><label>部署参数名称<input value={environmentKey} onChange={(e) => setEnvironmentKey(e.target.value)} /></label>
      <label>部署参数值<input value={environmentValue} onChange={(e) => setEnvironmentValue(e.target.value)} /></label></>}
    <label>供货方式<select value={supply} onChange={(e) => setSupply(e.target.value)}><option value="">保留原分配 / 新设备待确认</option>
      <option value="existing">已有设备</option><option value="purchase">采购</option><option value="unknown">待确认</option></select></label>
    {supply && <label>分配依据<input value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>}
    {error && <div className="error" role="alert">{error}</div>}
    <button onClick={confirm} disabled={busy}>预览当前行身份与业务设置</button>
    {preview && <NextEditPreview suggestion={preview} onApply={() => {
      try {
        onChanged(inWorkbookSession(host, { session,
          run: () => applyNextEdit({ host, suggestion: preview, operationId: crypto.randomUUID() }) }));
        setPreview(undefined);
      }
      catch (reason) { setError(String(reason)); }
    }} />}
  </details>;
}
