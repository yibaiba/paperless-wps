import { useState } from 'react';
import type { BusinessOperation, WorkbookBusinessContext } from '../businessTypes';
import type { HostAdapter } from '../host';
import type { TemplateProfile, WorkbookMetadata } from '../types';
import { assertWorkbookSession, captureWorkbookSession } from '../workbookSession';

export function BusinessSettings({ context, host, metadata, profile, onSaved }: {
  context: WorkbookBusinessContext; host: HostAdapter; metadata: WorkbookMetadata;
  profile: TemplateProfile; onSaved: (value: WorkbookMetadata) => void;
}) {
  const [systemId, setSystemId] = useState('');
  const [roomId, setRoomId] = useState('');
  const [roomName, setRoomName] = useState('');
  const [systemName, setSystemName] = useState('');
  const [packageId, setPackageId] = useState('');
  const [first, setFirst] = useState(String(host.activeCell().row));
  const [last, setLast] = useState(String(host.activeCell().row));
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [features, setFeatures] = useState<string[]>([]);
  const [purchase, setPurchase] = useState(false);
  const [evidence, setEvidence] = useState('');
  const [error, setError] = useState('');
  const [session] = useState(() => captureWorkbookSession(host));
  const packages = context.definitions.packages;
  const existingSystem = context.configuration.systems.find((s) => s.id === systemId);
  const selected = packages.find((p) => p.id === (existingSystem?.knowledge_package_id ?? packageId));
  const quantities = [...new Map((selected?.definition.roles ?? []).flatMap((r) => {
    const q = r.quantity_basis;
    return q?.input_key ? [[`${q.scope}:${q.input_key}`, q] as const] : [];
  })).entries()];
  const availableFeatures = [...new Set(selected?.definition.roles.map((r) => r.feature).filter(Boolean))];

  function attributes(scope: string) {
    const before = scope === 'system' ? existingSystem?.inputs ?? []
      : scope === 'room' ? context.configuration.room_inputs?.[existingSystem?.room_id ?? roomId] ?? []
        : context.configuration.project_inputs ?? [];
    const changed = quantities.filter(([key, q]) => q.scope === scope && key in inputs);
    return [...before.filter((a) => !changed.some(([, q]) => q.input_key === a.key)),
      ...changed.filter(([key]) => inputs[key].trim()).map(([key, q]) => ({
        key: q.input_key, kind: 'quantity', value: inputs[key], unit: q.input_unit,
      }))];
  }

  function save() {
    setError('');
    try {
      assertWorkbookSession(host, session);
      const actual = host.readMetadata();
      if (actual.pending_sync || host.journals().some((j) => ['prepared', 'recovery_required'].includes(j.state))) {
        throw new Error('请先恢复未完成的操作，再修改业务设置');
      }
      if (actual.binding?.binding_id !== metadata.binding?.binding_id
        || actual.business?.local_revision !== metadata.business?.local_revision) {
        throw new Error('工作簿业务设置已变化，请重新打开业务设置');
      }
      const start = Number(first), end = Number(last);
      if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start <= profile.header_row || end < start) {
        throw new Error('请填写表头之后的有效产品行范围');
      }
      const previous = metadata.business ?? { local_revision: 0, scopes: [], operations: [], recent_edits: [] };
      let system = context.configuration.systems.find((s) => s.id === systemId);
      const operations: BusinessOperation[] = [];
      if (!system) {
        if (!selected || !systemName.trim() || (!roomId && !roomName.trim())) throw new Error('请选择已发布版本，并填写房间和系统名称');
        const identity = roomId || crypto.randomUUID();
        system = { id: crypto.randomUUID(), name: systemName.trim(), kind: selected.name,
          room_id: identity, definition_id: selected.system_definition_id, knowledge_package_id: selected.id,
          inputs: attributes('system'), features };
        operations.push({ action: 'system_setup', system, features_confirmed: true,
          ...(roomId ? {} : { new_room: { id: identity, name: roomName.trim() } }),
          ...(attributes('room').length ? { room_inputs: attributes('room') } : {}),
          ...(attributes('project').length ? { project_inputs: attributes('project') } : {}),
          role_ids: selected.definition.roles.filter((r) => !r.feature || features.includes(r.feature)).map((r) => r.id) });
      } else if (selected && (Object.keys(inputs).length || JSON.stringify(features) !== JSON.stringify(system.features))) {
        system = { ...system, inputs: attributes('system'), features };
        operations.push({ action: 'system_setup', system, features_confirmed: true,
          ...(system.room_id ? { room_inputs: attributes('room') } : {}), project_inputs: attributes('project'),
          role_ids: selected.definition.roles.filter((r) => !r.feature || features.includes(r.feature)).map((r) => r.id) });
      }
      if (purchase) {
        if (!evidence.trim()) throw new Error('新增采购需要明确依据；否则请保持供货待确认');
        operations.push({ action: 'requirements_patch', generation: {
          ...context.configuration.generation, supply_source: 'purchase', supply_evidence: evidence,
          features_confirmed: [...new Set([
            ...((context.configuration.generation.features_confirmed ?? []) as string[]), system.id,
          ])],
        } });
      }
      const scope = { sheet: profile.sheet_selector, start_row: start, end_row: end,
        system_id: system.id, room_id: system.room_id };
      const overlaps = previous.scopes.filter((s) => s.sheet === scope.sheet && s.start_row <= end && s.end_row >= start);
      if (overlaps.some((s) => s.start_row !== start || s.end_row !== end)) throw new Error('业务区范围交叠，请使用原范围修改或选择互不重叠的产品行');
      const next: WorkbookMetadata = { ...metadata, schema_version: 2, business: {
        ...previous, local_revision: previous.local_revision + 1,
        scopes: [...previous.scopes.filter((s) => !overlaps.includes(s)), scope],
        operations: [...previous.operations, ...operations],
      } };
      host.writeMetadata(next); onSaved(next);
    } catch (reason) { setError(String(reason)); }
  }

  return <details className="business-settings" open={!metadata.business?.scopes.length}>
    <summary>业务区与固定系统版本</summary>
    <p>保存仅更新本地设置；设备行数量不等于房间人数。空参数将明确保持待确认。</p>
    <label>已有系统<select value={systemId} onChange={(e) => {
      setSystemId(e.target.value); setInputs({});
      setFeatures(context.configuration.systems.find((s) => s.id === e.target.value)?.features ?? []);
    }}>
      <option value="">新建系统</option>{context.configuration.systems.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.id}</option>)}
    </select></label>
    {!systemId && <>
      <label>房间<select value={roomId} onChange={(e) => setRoomId(e.target.value)}><option value="">新房间</option>
        {context.configuration.rooms.map((r) => <option key={r.id} value={r.id}>{r.name} · {r.id}</option>)}</select></label>
      {!roomId && <label>房间名称<input value={roomName} onChange={(e) => setRoomName(e.target.value)} /></label>}
      <label>系统名称<input value={systemName} onChange={(e) => setSystemName(e.target.value)} /></label>
      <label>绑定快照中的已发布知识包<select value={packageId} onChange={(e) => { setPackageId(e.target.value); setInputs({}); }}>
        <option value="">请选择</option>{packages.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      {!packages.length && <div className="issue">当前固定版本没有已发布知识包。请先在系统中确认资料、发布版本并明确重新绑定；不会自动采用草稿规则。</div>}
    </>}
    {quantities.map(([key, q]) => <label key={key}>{q.scope} · {q.input_key}（{q.input_unit || '单位未指定'}）
      <input inputMode="decimal" value={inputs[key] ?? attributes(q.scope).find((a) => a.key === q.input_key)?.value ?? ''}
        onChange={(e) => setInputs((v) => ({ ...v, [key]: e.target.value }))} /></label>)}
    {availableFeatures.map((feature) => <label key={feature}><input type="checkbox" checked={features.includes(feature)}
      onChange={(e) => setFeatures((values) => e.target.checked ? [...values, feature] : values.filter((v) => v !== feature))} />{feature}</label>)}
    <div className="form-row"><label>产品起始行<input type="number" value={first} onChange={(e) => setFirst(e.target.value)} /></label>
      <label>结束行<input type="number" value={last} onChange={(e) => setLast(e.target.value)} /></label></div>
    <label><input type="checkbox" checked={purchase} onChange={(e) => setPurchase(e.target.checked)} />新增缺项允许采购（已有设备供货方式不变）</label>
    {purchase && <label>采购依据<input value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>}
    {error && <div className="error" role="alert">{error}</div>}
    <button onClick={save}>确认并保存本地业务设置</button>
  </details>;
}
