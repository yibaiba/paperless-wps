import { CloudSyncOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useEffect, useState } from 'react';

import type { WpsApi } from '../api';
import { ApiError } from '../api';
import type { HostAdapter } from '../host';
import { scanWorkbook } from '../workbook';
import { businessSyncRequest } from '../businessWorkbook';
import { recoverSyncReceipt } from '../syncRecovery';
import { businessDiagnostic } from '../businessDiagnostics';
import { assertWorkbookSession, captureWorkbookSession, isWorkbookSession } from '../workbookSession';
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
  const [scan, setScan] = useState<ReturnType<typeof scanWorkbook>>({ lines: [], unresolved: [] });
  const [previewRevision, setPreviewRevision] = useState(-1);
  useEffect(() => host.onSheetChange(() => { setPreview(undefined); setOperationId(''); }), [host]);

  function request() {
    if (!metadata.binding) throw new Error('请先绑定项目');
    if (host.journals().some((j) => ['prepared', 'recovery_required'].includes(j.state))) {
      throw new Error('有未完成的本地编辑，请先恢复日志再同步');
    }
    const current = host.readMetadata();
    const fresh = scanWorkbook(host.readRows(profile), current);
    setScan(fresh);
    if (fresh.unresolved.length) throw new Error(fresh.unresolved.join('；'));
    return businessSyncRequest(current, fresh.lines);
  }

  async function loadPreview() {
    setBusy(true); setError(''); setPreview(undefined); setOperationId('');
    try {
      const session = captureWorkbookSession(host);
      const revision = host.businessRevision();
      const result = await api.preview(request());
      assertWorkbookSession(host, session);
      if (host.businessRevision() !== revision) throw new Error('工作簿在预览期间变化，请重新预览');
      setPreview(result);
      setPreviewRevision(revision);
      setOperationId(crypto.randomUUID());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setBusy(false); }
  }

  async function commit() {
    if ((!preview || !operationId) && !metadata.pending_sync) return;
    setBusy(true); setError('');
    const session = captureWorkbookSession(host);
    try {
      let current = host.readMetadata();
      if (!current.pending_sync) {
        if (host.businessRevision() !== previewRevision) throw new Error('预览后有编辑，请重新预览');
        current = { ...current, pending_sync: {
          request: { ...request(), preview_fingerprint: preview!.preview_fingerprint, operation_id: operationId },
          local_revision: previewRevision, operations: current.business?.operations ?? [], line_bindings: current.line_bindings,
        } };
        host.writeMetadata(current); onSynced(current);
      }
      const result = await api.commit(current.pending_sync!.request);
      assertWorkbookSession(host, session);
      const next = recoverSyncReceipt(host.readMetadata(), result);
      host.writeMetadata(next);
      onSynced(next);
      for (const journal of host.journals().filter((j) => j.state === 'applied'
        && j.patches.every((p) => host.readCell(p).value === p.after)
        && j.after.line_bindings.every((b) => next.line_bindings.some((line) =>
          line.line_id === b.line_id && line.variant_id === b.variant_id && line.source_id === b.source_id)))) {
        businessDiagnostic(host, { event_id: `${journal.operation_id}:retained`, event_type: 'completion_retained', outcome: 'success' });
      }
      setPreview(undefined);
      setOperationId('');
    } catch (reason) {
      if (reason instanceof ApiError && [409, 422].includes(reason.status) && isWorkbookSession(host, session)) {
        const current = { ...host.readMetadata(), pending_sync: undefined };
        host.writeMetadata(current); onSynced(current);
      }
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
      {metadata.pending_sync && <button onClick={commit} disabled={busy}>重试原操作 / 恢复同步回执</button>}
      <button onClick={loadPreview} disabled={busy || !metadata.binding || Boolean(metadata.pending_sync)}>预览差异</button>
      <button className="primary" onClick={commit} disabled={busy || !preview?.has_changes || Boolean(metadata.pending_sync)}>
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
