/** DSI import wizard: labels, gate rules, sample formatting (shared with tests). */

export function dsiTargetLabel(t: string): string {
  const labels: Record<string, string> = {
    transaction_date: 'Transaction / invoice date',
    snapshot_date: 'Inventory snapshot date',
    distributor_token: 'Distributor',
    dealer_group_token: 'Customer account',
    customer_dealer_token: 'Source customer name',
    product_identifier: 'Product identifier (SKU / part # / model)',
    quantity_sold: 'Quantity sold',
    unit_sellout_price_ex_tax_amount: 'Unit sell-out price ex tax / ex VAT',
    reported_revenue_amount: 'Reported line value / revenue',
    currency_code: 'Currency',
    stock_on_hand: 'Stock on hand',
    channel_key_token: 'Channel / route-to-market',
    region_or_province_token: 'Region / province',
    open_channel_evidence: 'Open Channel evidence',
    ignored_shipping_evidence: 'Ignored shipping-like evidence (preserved only)',
  };
  if (labels[t]) return labels[t];
  return t.replace(/_/g, ' ');
}

/** Longer helper text for mapping UI (tooltips / secondary lines). Only defined where naming needs context. */
export function dsiTargetDescription(t: string): string | undefined {
  const descriptions: Record<string, string> = {
    dealer_group_token:
      'Primary customer account for this import: rows roll up here for reporting, matching, and facts. On RAW workbooks map the Dealer Name Group column here—not the free-text customer name.',
    customer_dealer_token:
      'Secondary label from the file only: the raw customer / site name as printed (e.g. Customer name on RAW). Stored as alias and matching evidence under the Customer account, not as the rollup account.',
  };
  return descriptions[t];
}

export type DsiMappingStampOpts = {
  fileDistributorSatisfied?: boolean;
  fileSnapshotSatisfied?: boolean;
};

/** True when this sheet's date requirement is met only via confirmed Application Date stamps (not a date column). */
export function dsiDateSatisfiedBySnapshotStamp(
  m: Record<string, string>,
  opts?: Pick<DsiMappingStampOpts, 'fileSnapshotSatisfied'>
): boolean {
  const vals = new Set(Object.values(m).filter(Boolean));
  if (vals.has('transaction_date') || vals.has('snapshot_date')) return false;
  return vals.has('stock_on_hand') && Boolean(opts?.fileSnapshotSatisfied);
}

export function dsiGateFromMapping(m: Record<string, string>, opts?: DsiMappingStampOpts): boolean {
  const vals = new Set(Object.values(m).filter(Boolean));
  const distributorOk = vals.has('distributor_token') || Boolean(opts?.fileDistributorSatisfied);
  const needsInventoryPeriod = vals.has('stock_on_hand') && !vals.has('snapshot_date');
  const dateOk =
    vals.has('transaction_date') ||
    vals.has('snapshot_date') ||
    (needsInventoryPeriod && Boolean(opts?.fileSnapshotSatisfied));
  return (
    distributorOk &&
    vals.has('product_identifier') &&
    dateOk &&
    (vals.has('quantity_sold') || vals.has('stock_on_hand'))
  );
}

/**
 * Live requirement chips for CanonicalColumnMappingPanel.
 * Distributor and inventory Date may be satisfied by per-file stamps (same gate as dsiGateFromMapping).
 */
export function dsiMappingRequiredGroupsFromDraft(
  draft: Record<string, string>,
  opts: DsiMappingStampOpts & {
    baseGroups: Array<{ id: string; label: string; anyOf: string[]; externallySatisfied?: boolean }>;
  }
): Array<{ id: string; label: string; anyOf: string[]; externallySatisfied?: boolean }> {
  const dateFromStamp = dsiDateSatisfiedBySnapshotStamp(draft, opts);
  return opts.baseGroups.map((g) => {
    if (g.id === 'distributor') {
      return { ...g, externallySatisfied: Boolean(opts.fileDistributorSatisfied) };
    }
    if (g.id === 'date') {
      return { ...g, externallySatisfied: dateFromStamp };
    }
    return { ...g };
  });
}

/** True when every sheet in a nested (multi-sheet) mapping passes the flat gate. */
export function dsiGateFromNestedMapping(
  m: Record<string, Record<string, string>>,
  opts?: DsiMappingStampOpts
): boolean {
  const sheets = Object.values(m).filter((s) => s && Object.keys(s).length > 0);
  if (!sheets.length) return false;
  return sheets.every((sheet) => dsiGateFromMapping(sheet, opts));
}

export type DsiMissingRequirementId =
  | 'distributor'
  | 'product'
  | 'date'
  | 'quantity'
  | 'inventory_period';

export type DsiMissingRequirement = {
  id: DsiMissingRequirementId;
  label: string;
};

const MISSING_LABELS: Record<DsiMissingRequirementId, string> = {
  distributor: 'Distributor (column or per-file Dist stamp)',
  product: 'Product identifier',
  date: 'Transaction / invoice date (or Inventory snapshot date)',
  quantity: 'Quantity sold and/or stock on hand',
  inventory_period:
    'Inventory as-of period (confirm Application Date stamp, or map Inventory snapshot date)',
};

/**
 * Structured gaps for one sheet mapping — same rules as dsiGateFromMapping /
 * the Import Centre blocking banner (no new gate semantics).
 */
export function dsiSheetMissingRequirements(
  sheet: Record<string, string>,
  opts?: DsiMappingStampOpts
): DsiMissingRequirement[] {
  const vals = new Set(Object.values(sheet).filter(Boolean));
  const missing: DsiMissingRequirement[] = [];
  const distributorOk = vals.has('distributor_token') || Boolean(opts?.fileDistributorSatisfied);
  if (!distributorOk) {
    missing.push({ id: 'distributor', label: MISSING_LABELS.distributor });
  }
  if (!vals.has('product_identifier')) {
    missing.push({ id: 'product', label: MISSING_LABELS.product });
  }
  const needsInventoryPeriod = vals.has('stock_on_hand') && !vals.has('snapshot_date');
  const hasTxOrSnap = vals.has('transaction_date') || vals.has('snapshot_date');
  const dateOk =
    hasTxOrSnap || (needsInventoryPeriod && Boolean(opts?.fileSnapshotSatisfied));
  if (needsInventoryPeriod && !opts?.fileSnapshotSatisfied) {
    missing.push({ id: 'inventory_period', label: MISSING_LABELS.inventory_period });
  } else if (!dateOk) {
    missing.push({ id: 'date', label: MISSING_LABELS.date });
  }
  if (!vals.has('quantity_sold') && !vals.has('stock_on_hand')) {
    missing.push({ id: 'quantity', label: MISSING_LABELS.quantity });
  }
  return missing;
}

export type DsiLayoutFailure = {
  signature: string;
  label: string;
  keys: string[];
  representativeKey: string;
  missing: DsiMissingRequirement[];
};

export type DsiLayoutReadiness = {
  readyCount: number;
  total: number;
  failing: DsiLayoutFailure[];
};

/** Layout tab label used in tabs / banner (Layout N · K files, or solo key). */
export function dsiLayoutTabLabel(group: DsiLayoutTabGroup, index: number): string {
  if (group.keys.length > 1) {
    return `Layout ${index + 1} · ${group.keys.length} files`;
  }
  return group.keys[0] ?? group.signature;
}

/**
 * Per-layout gate readiness for multi-file / multi-sheet mapping.
 * A layout is ready when every member sheet passes dsiGateFromMapping.
 */
export function dsiLayoutReadiness(
  layoutGroups: DsiLayoutTabGroup[],
  nestedDraft: Record<string, Record<string, string>>,
  opts?: DsiMappingStampOpts
): DsiLayoutReadiness {
  const failing: DsiLayoutFailure[] = [];
  let readyCount = 0;
  layoutGroups.forEach((g, idx) => {
    const unionMissing = new Map<DsiMissingRequirementId, DsiMissingRequirement>();
    let groupOk = true;
    for (const k of g.keys) {
      const sheet = nestedDraft[k] ?? {};
      if (!dsiGateFromMapping(sheet, opts)) {
        groupOk = false;
        for (const m of dsiSheetMissingRequirements(sheet, opts)) {
          if (!unionMissing.has(m.id)) unionMissing.set(m.id, m);
        }
      }
    }
    if (groupOk) {
      readyCount += 1;
      return;
    }
    failing.push({
      signature: g.signature,
      label: dsiLayoutTabLabel(g, idx),
      keys: g.keys,
      representativeKey: g.representativeKey,
      missing: [...unionMissing.values()],
    });
  });
  return { readyCount, total: layoutGroups.length, failing };
}

/**
 * True when any nested sheet for this filename maps stock_on_hand without snapshot_date
 * (same intent as backend file_needs_snapshot_period_stamp).
 *
 * Prefer the client draft; fall back to server ``sheet_field_mappings[].field_mapping``
 * so the file strip still shows inventory periods before / without a hydrated draft.
 */
export function dsiFileNeedsInventoryPeriod(
  nestedDraft: Record<string, Record<string, string>>,
  filename: string,
  serverSheetFieldMappings?: Record<string, { field_mapping?: Record<string, string> }> | null
): boolean {
  const prefix = `${filename}::`;
  const fileMatches = (key: string) =>
    key === filename ||
    key.startsWith(prefix) ||
    (key.includes('::') && key.split('::')[0] === filename);

  const needsFromMap = (sheet: Record<string, string> | undefined) => {
    const vals = new Set(Object.values(sheet ?? {}).filter(Boolean));
    return vals.has('stock_on_hand') && !vals.has('snapshot_date');
  };

  for (const [key, sheet] of Object.entries(nestedDraft)) {
    if (!fileMatches(key)) continue;
    if (needsFromMap(sheet)) return true;
  }
  if (serverSheetFieldMappings) {
    for (const [key, wrap] of Object.entries(serverSheetFieldMappings)) {
      if (!fileMatches(key)) continue;
      if (needsFromMap(wrap?.field_mapping)) return true;
    }
  }
  return false;
}

export type DsiLayoutBlockingError = {
  code: string;
  message: string;
  signature: string;
  representativeKey: string;
  missingId: DsiMissingRequirementId;
};

/** Banner lines named by layout; dedupe by layout+missing kind (not bare code). */
export function formatDsiBlockingErrorsByLayout(
  readiness: DsiLayoutReadiness
): DsiLayoutBlockingError[] {
  const out: DsiLayoutBlockingError[] = [];
  const seen = new Set<string>();
  for (const f of readiness.failing) {
    for (const m of f.missing) {
      const dedupeKey = `${f.signature}::${m.id}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      out.push({
        code: `layout_${m.id}_${f.signature}`,
        message: `${f.label} — needs ${m.label}.`,
        signature: f.signature,
        representativeKey: f.representativeKey,
        missingId: m.id,
      });
    }
  }
  return out;
}

export type DsiLayoutGroup = {
  signature: string;
  mapping_keys: string[];
  files?: string[];
};

export type DsiLayoutTabGroup = {
  signature: string;
  keys: string[];
  representativeKey: string;
};

/**
 * Collapse sheet keys into layout tabs. Detached keys become singletons.
 * When layoutGroups is missing/empty, every key is its own group (legacy jobs).
 */
export function groupDsiSheetKeys(
  layoutGroups: DsiLayoutGroup[] | null | undefined,
  sheetKeys: string[],
  detachedKeys: Set<string> | Iterable<string>,
  drafts?: Record<string, Record<string, string>>
): DsiLayoutTabGroup[] {
  const detached = detachedKeys instanceof Set ? detachedKeys : new Set(detachedKeys);
  const keySet = new Set(sheetKeys);
  const pickRepresentative = (keys: string[]): string => {
    if (!drafts || keys.length === 1) return keys[0];
    let best = keys[0];
    let bestCount = -1;
    for (const k of keys) {
      const n = Object.values(drafts[k] ?? {}).filter(Boolean).length;
      if (n > bestCount) {
        bestCount = n;
        best = k;
      }
    }
    return best;
  };

  if (!layoutGroups?.length) {
    return sheetKeys.map((k) => ({
      signature: `solo:${k}`,
      keys: [k],
      representativeKey: k,
    }));
  }

  const out: DsiLayoutTabGroup[] = [];
  const consumed = new Set<string>();
  for (const g of layoutGroups) {
    const members = (g.mapping_keys ?? []).filter((k) => keySet.has(k) && !detached.has(k));
    if (!members.length) continue;
    for (const k of members) consumed.add(k);
    out.push({
      signature: g.signature,
      keys: members,
      representativeKey: pickRepresentative(members),
    });
  }
  for (const k of sheetKeys) {
    if (consumed.has(k)) continue;
    out.push({ signature: `solo:${k}`, keys: [k], representativeKey: k });
  }
  return out;
}

/** Fan a layout draft out to every member mapping key (presentation merge; storage stays nested). */
export function fanOutDsiLayoutDraft(
  prev: Record<string, Record<string, string>>,
  memberKeys: string[],
  draft: Record<string, string>
): Record<string, Record<string, string>> {
  const next = { ...prev };
  for (const k of memberKeys) {
    next[k] = { ...draft };
  }
  return next;
}

export function isNestedDsiFieldMapping(
  m: Record<string, string> | Record<string, Record<string, string>> | null | undefined
): m is Record<string, Record<string, string>> {
  if (!m || typeof m !== 'object') return false;
  return Object.values(m).some((v) => v != null && typeof v === 'object' && !Array.isArray(v));
}

/** Build one sheet's draft map from server state (canonical targets only). */
export function sheetDraftFromServer(
  serverSheet: Record<string, string> | undefined,
  canonSet: Set<string>
): Record<string, string> {
  const sheetNext: Record<string, string> = {};
  for (const [h, v] of Object.entries(serverSheet ?? {})) {
    if (v && canonSet.has(v)) sheetNext[h] = v;
  }
  return sheetNext;
}

/**
 * Hydrate nested DSI mapping drafts from server.
 * - `replace`: full sync when local draft is clean
 * - `fillMissing`: when dirty, only seed sheet keys the operator has not edited yet
 *   so tab switches / refetches cannot wipe in-progress maps
 */
export function hydrateDsiNestedMapDraft(args: {
  sheetKeys: string[];
  serverNested: Record<string, Record<string, string>>;
  sheetFieldMappings?: Record<string, { field_mapping?: Record<string, string> }> | null;
  prev: Record<string, Record<string, string>>;
  canonSet: Set<string>;
  mode: 'replace' | 'fillMissing';
}): Record<string, Record<string, string>> {
  const { sheetKeys, serverNested, sheetFieldMappings, prev, canonSet, mode } = args;
  if (mode === 'replace') {
    const next: Record<string, Record<string, string>> = {};
    for (const key of sheetKeys) {
      const serverSheet = sheetFieldMappings?.[key]?.field_mapping ?? serverNested[key] ?? {};
      next[key] = sheetDraftFromServer(serverSheet, canonSet);
    }
    return next;
  }
  const next: Record<string, Record<string, string>> = { ...prev };
  for (const key of sheetKeys) {
    const existing = next[key];
    if (existing && Object.keys(existing).length > 0) continue;
    const serverSheet = sheetFieldMappings?.[key]?.field_mapping ?? serverNested[key] ?? {};
    next[key] = sheetDraftFromServer(serverSheet, canonSet);
  }
  return next;
}

export function hydrateDsiFlatMapDraft(args: {
  fileHeaders: string[];
  server: Record<string, string>;
  prev: Record<string, string>;
  canonSet: Set<string>;
  mode: 'replace' | 'fillMissing';
}): Record<string, string> {
  const { fileHeaders, server, prev, canonSet, mode } = args;
  if (mode === 'replace') {
    const next: Record<string, string> = {};
    for (const h of fileHeaders) {
      const v = server[h];
      if (v && canonSet.has(v)) next[h] = v;
    }
    return next;
  }
  if (Object.keys(prev).length > 0) return prev;
  const next: Record<string, string> = {};
  for (const h of fileHeaders) {
    const v = server[h];
    if (v && canonSet.has(v)) next[h] = v;
  }
  return next;
}

export function formatDsiSamples(samples: string[] | undefined): string {
  if (!samples?.length) return '—';
  const parts = samples.map((s) => (s.length > 48 ? `${s.slice(0, 45)}…` : s)).filter(Boolean);
  return parts.length ? parts.join(', ') : '—';
}

/** MUI Select value: never pass a target not in the canonical allow-list. */
export function dsiSelectValue(raw: string | undefined, canonSet: Set<string>): string {
  const v = raw ?? '';
  return v && canonSet.has(v) ? v : '';
}

/** Stable JSON for field_mapping so gate keys match across renders / ref snapshots. */
export function stableFieldMappingJson(
  fieldMapping: Record<string, string> | Record<string, Record<string, string>> | undefined
): string {
  const m = fieldMapping ?? {};
  const sorted: Record<string, string | Record<string, string>> = {};
  for (const k of Object.keys(m).sort()) {
    const v = m[k];
    if (typeof v === 'string') {
      if (v) sorted[k] = v;
    } else if (v && typeof v === 'object') {
      const nested: Record<string, string> = {};
      for (const nestedKey of Object.keys(v).sort()) {
        if (v[nestedKey]) nested[nestedKey] = v[nestedKey];
      }
      if (Object.keys(nested).length > 0) sorted[k] = nested;
    }
  }
  return JSON.stringify(sorted);
}

export type DistributorSiSummary = {
  staging_rows?: number;
  blocking_rows?: number;
  human_fixable_blocking_rows?: number;
  master_merge_excluded_rows?: number;
  steward_map_blocking_rows?: number;
  /** Blank product token / mapping data-quality hard blocks (no steward candidate). */
  data_quality_blocking_rows?: number;
  auto_excluded_rows?: number;
  warning_rows?: number;
  aggregated_candidates?: number;
  import_mode?: string;
  /** Rows with sell-out blocked (missing customer or missing tx for non-zero qty), excluding hard distributor/product errors. */
  sellout_issue_rows?: number;
  /** Subset: inventory path is valid (SOH + snapshot) but sell-out still blocked — inventory may apply on apply. */
  rows_inventory_ready_with_sellout_warnings?: number;
};

/** All hard blocks that still gate Continue → apply (steward-map + data-quality). */
export function dsiHumanFixableBlockingRows(summary: DistributorSiSummary | null | undefined): number {
  if (!summary) return 0;
  return summary.human_fixable_blocking_rows ?? summary.blocking_rows ?? 0;
}

/** Rows that need steward entity mapping (not blank-token data-quality). */
export function dsiStewardMapBlockingRows(summary: DistributorSiSummary | null | undefined): number {
  if (!summary) return 0;
  if (summary.steward_map_blocking_rows != null) return summary.steward_map_blocking_rows;
  const total = dsiHumanFixableBlockingRows(summary);
  const dq = summary.data_quality_blocking_rows ?? 0;
  return Math.max(0, total - dq);
}

export function dsiDataQualityBlockingRows(summary: DistributorSiSummary | null | undefined): number {
  if (!summary) return 0;
  return summary.data_quality_blocking_rows ?? 0;
}

export function formatDsiBlockerSummaryLine(summary: DistributorSiSummary | null | undefined): string | null {
  if (!summary) return null;
  const master = summary.master_merge_excluded_rows ?? 0;
  const steward = dsiStewardMapBlockingRows(summary);
  const dataQuality = dsiDataQualityBlockingRows(summary);
  const auto = summary.auto_excluded_rows ?? 0;
  if (master === 0 && steward === 0 && dataQuality === 0 && auto === 0) return null;
  const parts = [
    `${master} master-merge`,
    `${steward} steward-map`,
    `${dataQuality} blank-product`,
    `${auto} auto-excluded`,
  ];
  return parts.join(' · ');
}

/** Parse distributor_si_summary row from import job preview rows (DSI validate). */
export function parseDistributorSiSummaryFromRows(
  previewRows: Array<{ row_number: number; code?: string; message?: string | null; id?: number }> | undefined
): DistributorSiSummary | null {
  if (!previewRows?.length) return null;
  const summaries = previewRows.filter(
    (r) => r.row_number === 0 && r.code === 'distributor_si_summary' && r.message
  );
  if (!summaries.length) return null;
  const withId = summaries.filter((r) => r.id != null);
  const row =
    withId.length > 0
      ? withId.reduce((best, r) => ((r.id ?? 0) > (best.id ?? 0) ? r : best))
      : summaries[summaries.length - 1];
  const raw = row.message;
  if (!raw) return null;
  const cut = raw.indexOf(' Applied sell-out');
  const jsonPart = cut === -1 ? raw : raw.slice(0, cut);
  try {
    return JSON.parse(jsonPart) as DistributorSiSummary;
  } catch {
    return null;
  }
}

/** Whether the Validate step may show “Continue to apply” (mapping + latest summary agree). */
export function dsiContinueToApplyAllowed(
  gateKey: string | null,
  jobId: number | null,
  fieldMapping: Record<string, string> | Record<string, Record<string, string>> | undefined,
  summary: DistributorSiSummary | null,
  opts: { isValidating: boolean; hasServerGate: boolean }
): boolean {
  if (!opts.hasServerGate || opts.isValidating) return false;
  if (jobId == null || gateKey === null || summary == null) return false;
  const key = `${jobId}::${stableFieldMappingJson(fieldMapping)}`;
  if (gateKey !== key) return false;
  if (dsiHumanFixableBlockingRows(summary) > 0) return false;
  return (summary.master_merge_excluded_rows ?? 0) === 0;
}

/** Gate key after a successful validate when blockers are cleared (null when apply must stay blocked). */
export function computeDsiContinueGateKey(
  jobId: number | null,
  fieldMapping: Record<string, string> | Record<string, Record<string, string>> | undefined,
  summary: DistributorSiSummary | null
): string | null {
  if (jobId == null || summary == null) return null;
  if (dsiHumanFixableBlockingRows(summary) > 0) return null;
  if ((summary.master_merge_excluded_rows ?? 0) > 0) return null;
  return `${jobId}::${stableFieldMappingJson(fieldMapping)}`;
}
