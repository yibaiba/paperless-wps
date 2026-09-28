import { useDraftPreview } from "../../projects/drafts/context";
import { startSheetMeasure } from './performance';
import { useEffect, useRef, useState } from 'react';
import { App } from 'antd';
import { assertPreviewVersion } from './previewVersion';
import { reviseEdit } from './batchReview';
import { api } from '../../../../shared/api';
import type { Checked, Configuration, ProjectConfiguration } from '../../types';
import { editOperations, PRICE_COLUMN, type CellEdit, type EditOperation } from './model';

export interface SheetContext {
  reviewing?: boolean;
  configuration: Configuration; saved: ProjectConfiguration; draftVersion: number;
  onChecked: (result: Checked) => void; onPending: (value: boolean) => void;
}
export interface EditPreview { draft_version: number; checked: Checked; changes: unknown[] }
export function useSheetEditing(context: SheetContext) {
  const draftPreview = useDraftPreview();
  const [pending, setPending] = useState<{ edits: CellEdit[]; version: number }>();
  const [preview, setPreview] = useState<EditPreview>();
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const generation = useRef(0);
  const previewOrigin = useRef<{ draft: number; project: number; generation: number } | null>(null);
  const live = useRef(context), inFlight = useRef(false), alive = useRef(true);
  live.current = context;
  const { message } = App.useApp();
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => () => context.onPending(false), [context.onPending]);
  useEffect(() => { context.onPending(busy || !!pending || !!context.reviewing); }, [busy, pending, context.reviewing, context.onPending]);
  const execute = async (operations: EditOperation[], apply: boolean) => {
    if (inFlight.current) return;
    const initial = live.current;
    const started = { draft: initial.draftVersion, project: initial.saved.revision, generation: generation.current };
    if (pending && pending.version !== initial.draftVersion) { setError('项目已修改，请取消本批次后重新选择。'); return; }
    inFlight.current = true; setBusy(true); setError('');
    try {
      const request = startSheetMeasure('edit-request');
      const result = draftPreview ? await draftPreview(operations, initial.draftVersion) : await api<EditPreview>(`/configuration/projects/${initial.saved.project_id}/edit-preview`, {
        method: 'POST', body: JSON.stringify({ configuration: initial.configuration,
          expected_revision: initial.saved.revision, draft_version: initial.draftVersion, operations }),
      });
      request();
      if (!alive.current) return;
      assertPreviewVersion(started, { draft: live.current.draftVersion, project: live.current.saved.revision,
        generation: generation.current }, result.draft_version);
      if (apply) initial.onChecked(result.checked); else { previewOrigin.current = started; setPreview(result); }
    } catch (cause) {
      const text = cause instanceof Error ? cause.message : String(cause);
      if (alive.current) { setError(text); void message.error(text); }
    } finally { inFlight.current = false; if (alive.current) setBusy(false); }
  };
  const edit = (edits: CellEdit[], batch: boolean) => {
    if (!edits.length || inFlight.current || pending) return;
    setError('');
    if (batch || edits.some((item) => item.column === PRICE_COLUMN || item.column === 4)) {
      setPending({ edits, version: live.current.draftVersion }); setPreview(undefined); return;
    }
    try { void execute(editOperations(live.current.configuration, edits, ''), true); }
    catch (cause) { setError(String(cause)); }
  };
  return { pending, preview, busy, error, edit, execute,
    revise: (target: CellEdit) => {
      if (inFlight.current) return;
      generation.current++;
      setPending((current) => current ? { ...current, edits: reviseEdit(current.edits, target) } : current);
      setPreview(undefined); setError('');
    },
    resetPreview: () => { generation.current++; setPreview(undefined); setError(''); },
    cancel: () => { if (!inFlight.current) { setPending(undefined); setPreview(undefined); setError(''); } },
    prepare: (evidence: string) => {
      setPreview(undefined);
      try { void execute(editOperations(live.current.configuration, pending!.edits, evidence), false); }
      catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    },
    apply: () => {
      if (!preview || !previewOrigin.current || preview.draft_version !== live.current.draftVersion) { setError('预览已过期，请重新编辑。'); return false; }
      try {
        assertPreviewVersion(previewOrigin.current, { draft: live.current.draftVersion,
          project: live.current.saved.revision, generation: generation.current }, preview.draft_version);
      } catch (cause) { setError(String(cause)); return false; }
      live.current.onChecked(preview.checked); setPending(undefined); setPreview(undefined); return true;
    },
  };
}
