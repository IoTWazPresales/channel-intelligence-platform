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
