/** Mirror of ``lineup_backfill_archive_config.parse_archive_relative_path`` for browser folder upload. */

export const DEFAULT_TENANT_BU_CODES = ['NB', 'NR', 'NV', 'NX', 'PF', 'XB'] as const;

export const ARCHIVE_EXCLUDE_NAME_SUBSTRINGS = ['do not use', 'previous q', 'kept as reference'] as const;

const LINEUP_EXTENSIONS = new Set(['.xlsx', '.xlsm', '.xls', '.csv']);

const YEAR_RE = /^20\d{2}$/;
const QUARTER_RE = /^Q[1-4]$/i;
const SHORT_QUARTER_RE = /^26Q[1-4]$/i;

export type ParsedArchivePath = {
  relativePath: string;
  folderPath: string | null;
  businessUnit: string | null;
  year: string | null;
  quarter: string | null;
};

function classifySegment(segment: string, tenantBuCodes: readonly string[]): string | null {
  const text = segment.trim();
  if (!text) return null;
  const upper = text.toUpperCase();
  if (tenantBuCodes.some((bu) => bu.toUpperCase() === upper)) return 'business_unit';
  if (YEAR_RE.test(text)) return 'year';
  if (QUARTER_RE.test(text) || SHORT_QUARTER_RE.test(text)) return 'quarter';
  return null;
}

export function parseArchiveRelativePath(
  relativePath: string,
  tenantBuCodes: readonly string[] = DEFAULT_TENANT_BU_CODES,
): ParsedArchivePath {
  const normalized = relativePath.replace(/\//g, '\\');
  const parts = normalized.split('\\').filter(Boolean);
  const dirParts = parts.length > 1 ? parts.slice(0, -1) : [];

  const found: Record<string, string> = {};
  for (const part of dirParts) {
    const role = classifySegment(part, tenantBuCodes);
    if (role && !found[role]) found[role] = part;
  }

  let quarter = found.quarter ?? null;
  if (quarter && SHORT_QUARTER_RE.test(quarter)) {
    quarter = `Q${quarter.slice(-1)}`;
  }

  const bu = found.business_unit ?? null;
  const year = found.year ?? null;
  const segments: string[] = [];
  if (bu) segments.push(bu);
  if (year) segments.push(year);
  if (quarter) segments.push(quarter.toUpperCase().startsWith('Q') ? quarter.toUpperCase() : quarter);

  return {
    relativePath: normalized,
    folderPath: segments.length ? segments.join('\\') : null,
    businessUnit: bu,
    year,
    quarter,
  };
}

export function isLineupArchiveFile(filename: string): boolean {
  const lower = filename.toLowerCase();
  if (lower.startsWith('~$')) return false;
  const dot = lower.lastIndexOf('.');
  if (dot < 0) return false;
  return LINEUP_EXTENSIONS.has(lower.slice(dot));
}

export function shouldExcludeLineupFile(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ARCHIVE_EXCLUDE_NAME_SUBSTRINGS.some((sub) => lower.includes(sub));
}

export type StagedLineupFile = {
  file: File;
  folderPath: string | null;
  relativePath: string;
};

export function stageLineupFilesFromList(
  list: FileList | File[],
  tenantBuCodes: readonly string[] = DEFAULT_TENANT_BU_CODES,
): StagedLineupFile[] {
  const out: StagedLineupFile[] = [];
  for (const file of Array.from(list)) {
    if (!isLineupArchiveFile(file.name) || shouldExcludeLineupFile(file.name)) continue;
    const webkitRelative =
      (file as File & { webkitRelativePath?: string }).webkitRelativePath?.trim() || file.name;
    const parsed = parseArchiveRelativePath(webkitRelative, tenantBuCodes);
    out.push({
      file,
      folderPath: parsed.folderPath,
      relativePath: parsed.relativePath,
    });
  }
  return out;
}

export function mergeStagedLineupFiles(
  existing: StagedLineupFile[],
  incoming: StagedLineupFile[],
  mode: 'append' | 'replace',
): StagedLineupFile[] {
  const base = mode === 'replace' ? [] : [...existing];
  const seen = new Set(base.map((s) => `${s.relativePath}:${s.file.size}`));
  for (const item of incoming) {
    const key = `${item.relativePath}:${item.file.size}`;
    if (seen.has(key)) continue;
    seen.add(key);
    base.push(item);
  }
  return base;
}
