export interface PreviewVersion { draft: number; project: number; generation: number }
export function assertPreviewVersion(started: PreviewVersion, current: PreviewVersion, returnedDraft: number) {
  if (started.draft !== returnedDraft || started.draft !== current.draft || started.project !== current.project || started.generation !== current.generation) {
    throw new Error('此编辑结果已过期，未覆盖后续修改。请重新编辑。');
  }
}
