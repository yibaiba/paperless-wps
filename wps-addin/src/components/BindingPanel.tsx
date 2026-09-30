import { LinkOutlined, PlusOutlined } from '@ant-design/icons';
import { useEffect, useState } from 'react';

import type { WpsApi } from '../api';
import type { HostAdapter } from '../host';
import type { BindingState, ProjectSummary, TemplateProfile, WorkbookMetadata } from '../types';

export function BindingPanel({ api, host, profile, metadata, onBound }: {
  api: WpsApi;
  host: HostAdapter;
  profile: TemplateProfile;
  metadata: WorkbookMetadata;
  onBound: (binding: BindingState) => void;
}) {
  const [mode, setMode] = useState<'new' | 'existing'>('new');
  const [name, setName] = useState('WPS 现场项目');
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectId, setProjectId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { api.projects().then((value) => setProjects(value.items)).catch(() => undefined); }, [api]);

  async function bind() {
    setBusy(true); setError('');
    try {
      const selected = projects.find((item) => item.id === projectId);
      if (mode === 'existing' && !selected) throw new Error('请选择需要绑定的项目');
      const result = await api.bind({
        workbook_instance_id: metadata.workbook_instance_id,
        name: selected?.name ?? name,
        ...(selected ? { project_id: selected.id, project_revision: selected.revision } : {}),
        template_profile_id: profile.id,
        template_profile_revision: profile.revision,
        operation_id: crypto.randomUUID(),
      });
      const productBindings = metadata.line_bindings.map(({ device_id: _, ...item }) => item);
      host.writeMetadata({
        ...metadata,
        profile_id: profile.id,
        profile_revision: profile.revision,
        binding: result,
        line_bindings: productBindings,
      });
      onBound(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setBusy(false); }
  }

  return <section className="panel-section" aria-labelledby="binding-title">
    <div className="section-heading">
      <div><h2 id="binding-title">绑定项目</h2><p>{metadata.binding ? '已绑定' : '未绑定'}</p></div>
    </div>
    <div className="segmented" role="group" aria-label="项目绑定方式">
      <button className={mode === 'new' ? 'active' : ''} onClick={() => setMode('new')}>
        <PlusOutlined />{metadata.binding ? '另存为新项目' : '新项目'}
      </button>
      <button className={mode === 'existing' ? 'active' : ''} onClick={() => setMode('existing')}>
        <LinkOutlined />已有项目
      </button>
    </div>
    {mode === 'new'
      ? <label>项目名称<input value={name} onChange={(event) => setName(event.target.value)} /></label>
      : <label>项目<select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
          <option value="">请选择</option>
          {projects.map((project) => <option key={project.id} value={project.id}>
            {project.name} · v{project.revision}
          </option>)}
        </select></label>}
    {error ? <div className="error" role="alert">{error}</div> : null}
    <button className="primary" onClick={bind} disabled={busy || !name.trim()}>
      <LinkOutlined />{busy ? '绑定中' : metadata.binding ? '重新绑定' : '确认绑定'}
    </button>
  </section>;
}
