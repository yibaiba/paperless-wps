import { EyeOutlined, SaveOutlined } from '@ant-design/icons';
import { useEffect, useMemo, useState } from 'react';

import type { WpsApi } from '../api';
import type { HostAdapter } from '../host';
import { validateMappedHeaders, validateMapping } from '../mappingValidation';
import type { ManagedField, SheetRow, TemplateField, TemplateProfile } from '../types';

const FIELDS: Array<[TemplateField, string]> = [
  ['model', '产品型号'], ['name', '产品名称'], ['description', '产品说明'],
  ['quantity', '数量'], ['unit', '单位'], ['brand', '品牌'], ['price', '单价'],
  ['note', '备注'], ['section', '分区/系统'],
];
const MANAGED = new Set<TemplateField>(['model', 'name', 'description', 'unit', 'brand', 'price']);

export function MappingPanel({ host, api, profiles, profile, onSelected, onSaved }: {
  host: HostAdapter;
  api: WpsApi;
  profiles: TemplateProfile[];
  profile?: TemplateProfile;
  onSelected: (profile?: TemplateProfile) => void;
  onSaved: (profile: TemplateProfile) => void;
}) {
  const sheets = useMemo(() => host.sheetNames(), [host]);
  const [sheet, setSheet] = useState(profile?.sheet_selector ?? host.activeCell().sheet);
  const [headerRow, setHeaderRow] = useState(profile?.header_row ?? 1);
  const [name, setName] = useState(profile?.name ?? '现场报价模板');
  const [mapping, setMapping] = useState<Partial<Record<TemplateField, number>>>(
    profile?.field_columns ?? {},
  );
  const [managed, setManaged] = useState<ManagedField[]>(profile?.managed_fields ?? []);
  const [headers, setHeaders] = useState<string[]>([]);
  const [previewRows, setPreviewRows] = useState<SheetRow[]>([]);
  const [previewSignature, setPreviewSignature] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const draftSignature = JSON.stringify({ sheet, headerRow, mapping, managed });

  useEffect(() => {
    try {
      setHeaders(host.readHeader(sheet, headerRow));
    } catch (reason) {
      setHeaders([]);
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [host, sheet, headerRow]);
  useEffect(() => {
    if (!profile) {
      setName('现场报价模板'); setMapping({}); setManaged([]);
      return;
    }
    setSheet(profile.sheet_selector);
    setHeaderRow(profile.header_row);
    setName(profile.name);
    setMapping(profile.field_columns);
    setManaged(profile.managed_fields);
    setPreviewRows([]);
    setPreviewSignature('');
  }, [profile]);

  function preview() {
    setError('');
    try {
      validateMapping(mapping, managed);
      validateMappedHeaders(mapping, headers);
      const draft: TemplateProfile = {
        id: profile?.id ?? 'preview',
        revision: profile?.revision ?? 1,
        schema_version: 1,
        name,
        sheet_selector: sheet,
        header_row: headerRow,
        field_columns: mapping,
        managed_fields: managed,
        normalized_header_fingerprint: '',
        created_by: '',
      };
      const rows = host.readRows(draft).slice(0, 5);
      setPreviewRows(rows);
      setPreviewSignature(draftSignature);
    } catch (reason) {
      setPreviewRows([]);
      setPreviewSignature('');
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function save() {
    setBusy(true); setError('');
    try {
      if (previewSignature !== draftSignature) throw new Error('字段映射变化后需要重新预览');
      const result = await api.saveTemplate({
        ...(profile ? { profile_id: profile.id, expected_revision: profile.revision } : {}),
        name,
        sheet_selector: sheet,
        header_row: headerRow,
        field_columns: mapping,
        managed_fields: managed,
        header_values: headers,
      });
      onSaved(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setBusy(false); }
  }

  return <section className="panel-section" aria-labelledby="mapping-title">
    <div className="section-heading">
      <div><h2 id="mapping-title">模板映射</h2><p>{profile ? `修订 v${profile.revision}` : '新模板'}</p></div>
    </div>
    {profiles.length ? <label>已有模板<select
      value={profile ? `${profile.id}:${profile.revision}` : ''} onChange={(event) => {
      const selected = profiles.find((item) => `${item.id}:${item.revision}` === event.target.value);
      onSelected(selected);
    }}>
      <option value="">新建模板</option>
      {profiles.map((item) => <option key={`${item.id}:${item.revision}`} value={`${item.id}:${item.revision}`}>
        {item.name} · v{item.revision}
      </option>)}
    </select></label> : null}
    <label>模板名称<input value={name} onChange={(event) => setName(event.target.value)} /></label>
    <div className="two-columns">
      <label>工作表<select value={sheet} onChange={(event) => setSheet(event.target.value)}>
        {sheets.map((item) => <option key={item}>{item}</option>)}
      </select></label>
      <label>表头行<input type="number" min="1" value={headerRow}
        onChange={(event) => setHeaderRow(Number(event.target.value))} /></label>
    </div>
    <div className="mapping-grid">
      {FIELDS.map(([field, label]) => <div className="mapping-row" key={field}>
        <span>{label}</span>
        <select aria-label={`${label}列`} value={mapping[field] ?? ''} onChange={(event) => {
          const value = Number(event.target.value);
          setMapping((current) => ({ ...current, [field]: value || undefined }));
        }}>
          <option value="">未映射</option>
          {headers.map((header, index) => <option value={index + 1} key={`${index}-${header}`}>
            {index + 1}. {header || '空列'}
          </option>)}
        </select>
        {MANAGED.has(field) ? <label className="check-label">
          <input type="checkbox" checked={managed.includes(field as ManagedField)}
            disabled={!mapping[field]} onChange={(event) => setManaged((current) => event.target.checked
              ? [...current, field as ManagedField]
              : current.filter((item) => item !== field))} />插件填写
        </label> : <span />}
      </div>)}
    </div>
    <button onClick={preview} disabled={busy}><EyeOutlined />预览解析结果</button>
    {previewSignature === draftSignature ? <div className="mapping-preview">
      <div className="preview-title"><EyeOutlined />
        {previewRows.length ? `已验证 ${previewRows.length} 行` : '已验证表头和字段列'}
      </div>
      {!previewRows.length ? <div className="mapping-empty">当前模板没有产品行，保存后可直接在空白行使用联想。</div> : null}
      {previewRows.map((row) => <div className="preview-row" key={`${row.sheet}:${row.row}`}>
        <span>{row.row}</span>
        <strong>{row.values.model || row.values.name}</strong>
        <span>{row.values.quantity || '数量为空'}</span>
      </div>)}
    </div> : null}
    {error ? <div className="error" role="alert">{error}</div> : null}
    <button className="primary" onClick={save} disabled={busy || previewSignature !== draftSignature}>
      <SaveOutlined />{busy ? '保存中' : '保存映射'}
    </button>
  </section>;
}
