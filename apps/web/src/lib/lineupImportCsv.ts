/**
 * Client-side CSV → payload rows for POST /api/v1/lineup/items/bulk.
 * XLSX should be exported to CSV first (or parsed elsewhere into the same row shape).
 */

export type LineupBulkApiRow = {
  customer_code: string;
  channel_code?: string | null;
  period_start: string;
  period_label?: string | null;
  sku: string;
  predecessor_sku?: string | null;
  successor_sku?: string | null;
  planned_range_summary?: string | null;
  current_range_summary?: string | null;
  planned_launch_date?: string | null;
  planned_eol_date?: string | null;
  planned_volume_units?: number;
  current_volume_units?: number | null;
  overlap_cannibalization_flag?: boolean;
  whitespace_gap_flag?: boolean;
  approval_status?: string | null;
  notes?: string | null;
};

/** Split one CSV record respecting double-quoted fields with escaped quotes (""). */
export function splitCsvRecord(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let i = 0;
  let inQuotes = false;
  while (i < line.length) {
    const c = line[i]!;
    if (inQuotes) {
      if (c === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i += 1;
        continue;
      }
      cur += c;
      i += 1;
      continue;
    }
    if (c === '"') {
      inQuotes = true;
      i += 1;
      continue;
    }
    if (c === ',') {
      out.push(cur);
      cur = '';
      i += 1;
      continue;
    }
    cur += c;
    i += 1;
  }
  out.push(cur);
  return out;
}

function normHeader(h: string): string {
  return h.trim().toLowerCase().replace(/\s+/g, '_');
}

const HEADER_ALIASES: Record<string, keyof LineupBulkApiRow | 'skip'> = {
  customer_code: 'customer_code',
  customer: 'customer_code',
  cust_code: 'customer_code',
  channel_code: 'channel_code',
  channel: 'channel_code',
  chan_code: 'channel_code',
  period_start: 'period_start',
  period: 'period_start',
  plan_period: 'period_start',
  period_start_date: 'period_start',
  period_label: 'period_label',
  sku: 'sku',
  product_sku: 'sku',
  product: 'sku',
  predecessor_sku: 'predecessor_sku',
  predecessor: 'predecessor_sku',
  pred_sku: 'predecessor_sku',
  successor_sku: 'successor_sku',
  successor: 'successor_sku',
  succ_sku: 'successor_sku',
  planned_range_summary: 'planned_range_summary',
  planned_range: 'planned_range_summary',
  planned_status: 'approval_status',
  current_range_summary: 'current_range_summary',
  current_range: 'current_range_summary',
  planned_launch_date: 'planned_launch_date',
  launch_timing: 'planned_launch_date',
  planned_date: 'planned_launch_date',
  launch_date: 'planned_launch_date',
  planned_eol_date: 'planned_eol_date',
  end_of_life_timing: 'planned_eol_date',
  eol_timing: 'planned_eol_date',
  eol_date: 'planned_eol_date',
  planned_volume_units: 'planned_volume_units',
  planned_volume: 'planned_volume_units',
  vol_plan: 'planned_volume_units',
  volume_plan: 'planned_volume_units',
  current_volume_units: 'current_volume_units',
  current_volume: 'current_volume_units',
  overlap_cannibalization_flag: 'overlap_cannibalization_flag',
  overlap: 'overlap_cannibalization_flag',
  whitespace_gap_flag: 'whitespace_gap_flag',
  whitespace: 'whitespace_gap_flag',
  approval_status: 'approval_status',
  status: 'approval_status',
  notes: 'notes',
  comment: 'notes',
};

function parseBoolCell(raw: string): boolean | undefined {
  const s = raw.trim().toLowerCase();
  if (s === '') return undefined;
  if (['1', 'true', 'yes', 'y', 'on'].includes(s)) return true;
  if (['0', 'false', 'no', 'n', 'off'].includes(s)) return false;
  return undefined;
}

function parseNumberCell(raw: string): number | undefined {
  const s = raw.trim();
  if (s === '') return undefined;
  const n = Number(s.replace(/,/g, ''));
  return Number.isFinite(n) ? n : undefined;
}

export type ParseLineupCsvResult = {
  rows: LineupBulkApiRow[];
  /** 1-based line numbers in the paste buffer for data rows (excluding header). */
  parseWarnings: { line: number; message: string }[];
  headerErrors: string[];
};

export function parseLineupImportCsv(text: string): ParseLineupCsvResult {
  const lines = text.split(/\r?\n/).filter((ln) => ln.trim() !== '');
  const headerErrors: string[] = [];
  const parseWarnings: { line: number; message: string }[] = [];
  if (lines.length === 0) {
    headerErrors.push('CSV is empty');
    return { rows: [], parseWarnings, headerErrors };
  }

  const headerCells = splitCsvRecord(lines[0]!).map(normHeader);
  const colKeys: (keyof LineupBulkApiRow | null)[] = [];
  const used = new Set<string>();
  for (const h of headerCells) {
    if (!h) {
      colKeys.push(null);
      continue;
    }
    const key = HEADER_ALIASES[h];
    if (key === 'skip' || key === undefined) {
      colKeys.push(null);
      if (h && !used.has(`unknown:${h}`)) {
        used.add(`unknown:${h}`);
        parseWarnings.push({ line: 1, message: `Unknown column "${h}" ignored` });
      }
      continue;
    }
    colKeys.push(key);
  }

  const need: (keyof LineupBulkApiRow)[] = ['customer_code', 'period_start', 'sku'];
  for (const k of need) {
    if (!colKeys.includes(k)) {
      headerErrors.push(`Missing required column for ${k} (use standard name or a supported alias)`);
    }
  }
  if (headerErrors.length) {
    return { rows: [], parseWarnings, headerErrors };
  }

  const rows: LineupBulkApiRow[] = [];
  for (let li = 1; li < lines.length; li += 1) {
    const lineNum = li + 1;
    const cells = splitCsvRecord(lines[li]!);
    if (cells.every((c) => c.trim() === '')) continue;

    const acc: Partial<LineupBulkApiRow> = {};
    for (let ci = 0; ci < colKeys.length; ci += 1) {
      const field = colKeys[ci];
      if (!field) continue;
      const raw = cells[ci] ?? '';
      const trimmed = raw.trim();
      if (field === 'overlap_cannibalization_flag' || field === 'whitespace_gap_flag') {
        const b = parseBoolCell(raw);
        if (b !== undefined) (acc as Record<string, unknown>)[field] = b;
        else if (trimmed !== '') parseWarnings.push({ line: lineNum, message: `Non-boolean ${field} "${trimmed}" ignored` });
        continue;
      }
      if (field === 'planned_volume_units' || field === 'current_volume_units') {
        const n = parseNumberCell(raw);
        if (n !== undefined) (acc as Record<string, unknown>)[field] = n;
        else if (trimmed !== '') parseWarnings.push({ line: lineNum, message: `Non-numeric ${field} "${trimmed}" ignored` });
        continue;
      }
      if (trimmed === '') continue;
      (acc as Record<string, string>)[field] = trimmed;
    }

    const customer_code = acc.customer_code?.trim() ?? '';
    const period_start = acc.period_start?.trim() ?? '';
    const sku = acc.sku?.trim() ?? '';
    if (!customer_code || !period_start || !sku) {
      parseWarnings.push({ line: lineNum, message: 'Skipped row: customer_code, period_start, and sku must be non-empty' });
      continue;
    }

    rows.push({
      customer_code,
      channel_code: acc.channel_code?.trim() || undefined,
      period_start,
      period_label: acc.period_label?.trim() || undefined,
      sku,
      predecessor_sku: acc.predecessor_sku?.trim() || undefined,
      successor_sku: acc.successor_sku?.trim() || undefined,
      planned_range_summary: acc.planned_range_summary?.trim() || undefined,
      current_range_summary: acc.current_range_summary?.trim() || undefined,
      planned_launch_date: acc.planned_launch_date?.trim() || undefined,
      planned_eol_date: acc.planned_eol_date?.trim() || undefined,
      planned_volume_units: acc.planned_volume_units,
      current_volume_units: acc.current_volume_units ?? null,
      overlap_cannibalization_flag: acc.overlap_cannibalization_flag,
      whitespace_gap_flag: acc.whitespace_gap_flag,
      approval_status: acc.approval_status?.trim() || undefined,
      notes: acc.notes?.trim() || undefined,
    });
  }

  return { rows, parseWarnings, headerErrors };
}
