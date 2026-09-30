import type { LineBinding, TemplateProfile, WorkbookLine } from './types';

const encoder = new TextEncoder();

export function normalizeHeader(value: string) { return value.replace(/\s+/g, '').toLocaleLowerCase(); }

export async function headerFingerprint(values: string[]) {
  const input = values.map(normalizeHeader).join('\0');
  const bytes = await crypto.subtle.digest('SHA-256', encoder.encode(input));
  return Array.from(new Uint8Array(bytes), (value) => value.toString(16).padStart(2, '0')).join('');
}

export function anchorFingerprint(line: Pick<WorkbookLine, 'model' | 'name'>) {
  return [line.model.trim(), line.name.trim()].join('\0').toLocaleLowerCase();
}

export function reconcileLineBindings(lines: WorkbookLine[], bindings: LineBinding[]) {
  const byRow = new Map(lines.map((line) => [`${line.sheet}:${line.row}`, line]));
  const byAnchor = new Map<string, WorkbookLine[]>();
  for (const line of lines) {
    const anchor = anchorFingerprint(line);
    byAnchor.set(anchor, [...(byAnchor.get(anchor) ?? []), line]);
  }
  return bindings.flatMap((binding) => {
    const atRow = byRow.get(`${binding.sheet}:${binding.row}`);
    if (atRow && (!binding.anchor_fingerprint || anchorFingerprint(atRow) === binding.anchor_fingerprint)) {
      return [{ ...binding, row: atRow.row }];
    }
    const matches = binding.anchor_fingerprint ? byAnchor.get(binding.anchor_fingerprint) ?? [] : [];
    return matches.length === 1
      ? [{ ...binding, sheet: matches[0].sheet, row: matches[0].row }]
      : [];
  });
}

export async function matchingProfile(
  profiles: TemplateProfile[], readHeader: (profile: TemplateProfile) => Promise<string[]>,
) {
  for (const profile of profiles) {
    if (await headerFingerprint(await readHeader(profile)) === profile.normalized_header_fingerprint) {
      return profile;
    }
  }
  return undefined;
}
