import type {
  ActiveCell, Candidate, LineBinding, SheetRow, TemplateProfile, WorkbookMetadata,
} from './types';
import { rowAnchor } from './workbook.ts';

export interface CandidateWriter {
  readRows(profile: TemplateProfile): SheetRow[];
  writeCandidate(profile: TemplateProfile, row: number, candidate: Candidate): void;
  writeMetadata(value: WorkbookMetadata): void;
}

interface CandidateAcceptance {
  host: CandidateWriter;
  profile: TemplateProfile;
  cell: ActiveCell;
  metadata: WorkbookMetadata;
  candidate: Candidate;
  section?: string;
  lineBinding?: LineBinding | null;
}

export function applyCandidate(options: CandidateAcceptance) {
  const {
    host, profile, cell, metadata, candidate,
  } = options;
  host.writeCandidate(profile, cell.row, candidate);
  const row = host.readRows(profile).find((item) => item.row === cell.row);
  if (!row) throw new Error('写入后未找到当前产品行');
  const exact = metadata.line_bindings.find((item) =>
    item.sheet === row.sheet && item.row === row.row);
  const previous = options.lineBinding === undefined ? exact : options.lineBinding ?? undefined;
  const binding: LineBinding = {
    line_id: previous?.line_id ?? crypto.randomUUID(),
    sheet: row.sheet,
    row: row.row,
    section: options.section?.trim() ?? previous?.section ?? '',
    anchor_fingerprint: rowAnchor(row),
    device_id: previous?.device_id,
    variant_id: candidate.variant_id,
    source_id: candidate.source_id,
  };
  const next = {
    ...metadata,
    profile_id: profile.id,
    profile_revision: profile.revision,
    line_bindings: [
      ...metadata.line_bindings.filter((item) => item.line_id !== binding.line_id
        && !(previous?.row === binding.row
          && item.sheet === binding.sheet && item.row === binding.row)),
      binding,
    ],
  };
  host.writeMetadata(next);
  return next;
}
