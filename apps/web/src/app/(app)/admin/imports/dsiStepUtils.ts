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

export function dsiGateFromMapping(
  m: Record<string, string>,
  opts?: { fileDistributorSatisfied?: boolean; fileSnapshotSatisfied?: boolean }
): boolean {
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

/** True when every sheet in a nested (multi-sheet) mapping passes the flat gate. */
export function dsiGateFromNestedMapping(
  m: Record<string, Record<string, string>>,
  opts?: { fileDistributorSatisfied?: boolean; fileSnapshotSatisfied?: boolean }
): boolean {
  const sheets = Object.values(m).filter((s) => s && Object.keys(s).length > 0);
  if (!sheets.length) return false;
  return sheets.every((sheet) => dsiGateFromMapping(sheet, opts));
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
export function stableFieldMappingJson(fieldMapping: Record<string, string> | undefined): string {
  const m = fieldMapping ?? {};
  const sorted: Record<string, string> = {};
  for (const k of Object.keys(m).sort()) {
    const v = m[k];
    if (v) sorted[k] = v;
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
  fieldMapping: Record<string, string> | undefined,
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
  fieldMapping: Record<string, string> | undefined,
  summary: DistributorSiSummary | null
): string | null {
  if (jobId == null || summary == null) return null;
  if (dsiHumanFixableBlockingRows(summary) > 0) return null;
  if ((summary.master_merge_excluded_rows ?? 0) > 0) return null;
  return `${jobId}::${stableFieldMappingJson(fieldMapping)}`;
}
