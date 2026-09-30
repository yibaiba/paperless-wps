import { CloudSyncOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useMemo, useState } from 'react';

import type { WpsApi } from '../api';
import type { HostAdapter } from '../host';
import { scanWorkbook } from '../workbook';
import type { SyncPreviewResult, TemplateProfile, WorkbookMetadata } from '../types';

export function SyncPanel({ api, host, profile, metadata, onSynced }: {
  api: WpsApi;
  host: HostAdapter;
  profile: TemplateProfile;
  metadata: WorkbookMetadata;
  onSynced: (metadata: WorkbookMetadata) => void;
}) {
  const [preview, setPreview] = useState<SyncPreviewResult>();
  const [operationId, setOperationId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const scan = useMemo(
    () => scanWorkbook(host.readRows(profile), metadata),
    [host, metadata, profile],
  );

  function request() {
    if (!metadata.binding) throw new Error('请先绑定项目');
    return {
      binding_id: metadata.binding.binding_id,
      expected_draft_revision: metadata.binding.draft_revision,
      expected_project_revision: metadata.binding.base_revision,
      template_profile_revision: profile.revision,
      known_device_ids: metadata.binding.managed_device_ids,
      lines: scan.lines,
    };
  }

  async function loadPreview() {
    setBusy(true); setError(''); setPreview(undefined); setOperationId('');
    try {
      if (scan.unresolved.length) throw new Error(scan.unresolved.join('；'));
      const result = await api.preview(request());
      setPreview(result);
      setOperationId(crypto.randomUUID());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setBusy(false); }
  }

  async function commit() {
    if (!preview || !operationId) return;
    setBusy(true); setError('');
    try {
      const result = await api.commit({
        ...request(), preview_fingerprint: preview.preview_fingerprint, operation_id: operationId,
      });
      const next: WorkbookMetadata = {
        ...metadata,
        binding: result,
        line_bindings: result.line_bindings.map((item) => {
          const line = scan.lines.find((value) => value.line_id === item.line_id);
          return { ...item, anchor_fingerprint: line
            ? [line.model, line.name].join('\0').toLocaleLowerCase() : undefined };
        }),
      };
      host.writeMetadata(next);
      onSynced(next);
      setPreview(undefined);
      setOperationId('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setBusy(false); }
  }

  return <section className="panel-section" aria-labelledby="sync-title">
    <div className="section-heading">
      <div><h2 id="sync-title">同步项目</h2>
        <p>{metadata.binding
          ? `项目 ${metadata.binding.project_id ?? '待创建'} · 基线 v${metadata.binding.base_revision}`
          : '尚未绑定项目'}</p>
      </div><CloudSyncOutlined />
    </div>
    <div className="sync-summary">
      <span><strong>{scan.lines.length}</strong> 已确认行</span>
      <span className={scan.unresolved.length ? 'danger-text' : ''}>
        <strong>{scan.unresolved.length}</strong> 待处理行
      </span>
    </div>
    {scan.unresolved.slice(0, 4).map((item) => <div className="issue" key={item}>{item}</div>)}
    {preview ? <div className="preview-block">
      <div className="preview-title"><SafetyCertificateOutlined />同步预览</div>
      <div className="sync-summary">
        <span><strong>{preview.changes.length}</strong> 项业务变化</span>
        <span><strong>{preview.issues.length}</strong> 项检查问题</span>
      </div>
      {preview.changes.map((change) => <details className="change" key={`${change.kind}:${change.id}`}>
        <summary>
          <span>{changeLabel(change.before, change.after)} · {change.kind}</span><code>{change.id}</code>
        </summary>
        <div className="change-values">
          <div><span>同步前</span><pre>{formatValue(change.before)}</pre></div>
          <div><span>同步后</span><pre>{formatValue(change.after)}</pre></div>
        </div>
      </details>)}
      {preview.issues.map((issue, index) => <div className="issue" key={index}>
        {formatValue(issue)}
      </div>)}
    </div> : null}
    {error ? <div className="error" role="alert">{error}</div> : null}
    <div className="button-row">
      <button onClick={loadPreview} disabled={busy || !metadata.binding}>预览差异</button>
      <button className="primary" onClick={commit} disabled={busy || !preview?.has_changes}>
        <CloudSyncOutlined />{busy ? '处理中' : '确认同步'}
      </button>
    </div>
  </section>;
}

function changeLabel(before: unknown, after: unknown) {
  if (before == null) return '新增';
  if (after == null) return '删除';
  return '修改';
}

function formatValue(value: unknown) {
  if (value == null) return '无';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}
