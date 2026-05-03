/** DSI import wizard: labels, gate rules, sample formatting (shared with tests). */

export function dsiTargetLabel(t: string): string {
  const labels: Record<string, string> = {
    transaction_date: 'Transaction / invoice date',
    snapshot_date: 'Inventory snapshot date',
    distributor_token: 'Distributor',
    customer_dealer_token: 'Customer / dealer / reseller',
    dealer_group_token: 'Dealer / customer group',
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

export function dsiGateFromMapping(m: Record<string, string>): boolean {
  const vals = new Set(Object.values(m).filter(Boolean));
  return (
    vals.has('distributor_token') &&
    vals.has('product_identifier') &&
    (vals.has('transaction_date') || vals.has('snapshot_date')) &&
    (vals.has('quantity_sold') || vals.has('stock_on_hand'))
  );
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
  warning_rows?: number;
  aggregated_candidates?: number;
  import_mode?: string;
  /** Rows with sell-out blocked (missing customer or missing tx for non-zero qty), excluding hard distributor/product errors. */
  sellout_issue_rows?: number;
  /** Subset: inventory path is valid (SOH + snapshot) but sell-out still blocked — inventory may apply on apply. */
  rows_inventory_ready_with_sellout_warnings?: number;
};

/** Parse distributor_si_summary row from import job preview rows (DSI validate). */
export function parseDistributorSiSummaryFromRows(
  previewRows: Array<{ row_number: number; code?: string; message?: string | null }> | undefined
): DistributorSiSummary | null {
  if (!previewRows?.length) return null;
  const row = previewRows.find((r) => r.row_number === 0 && r.code === 'distributor_si_summary');
  if (!row?.message) return null;
  const raw = row.message;
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
  return (summary.blocking_rows ?? 0) === 0;
}
