/**
 * Pure formatters and small helpers for the Commercial Planner page.
 * Kept out of `app/.../page.tsx` because Next.js App Router pages must not export arbitrary helpers.
 */

const BLOCKING_ECONOMICS_FLAGS = new Set([
  'missing_sku_assumption',
  'missing_or_invalid_landed_cost',
  'missing_or_invalid_controlled_cost',
  'invalid_fx_rate_to_usd',
  'invalid_fx_plan_currency_per_cost_currency',
  'impossible_economics',
  'non_positive_target_units',
  'non_positive_target_srp',
]);

/**
 * Format a stored margin/percentage value for display.
 * Convention: values < 1.0 are stored as decimal fractions (0.0724 = 7.24%);
 * values >= 1.0 are already percentage points (7.24 = 7.24%).
 * This threshold is safe for realistic disti/dealer margins in the 0–30% range.
 */
export function fmtMarginPct(v: number | null | undefined): string {
  if (v == null) return '—';
  const pct = v < 1.0 ? v * 100 : v;
  return `${pct.toFixed(2)}%`;
}

/** Format a local-currency price value with 2 decimal places. */
export function fmtCurrency(v: number | null | undefined): string {
  if (v == null) return '—';
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** When API omits `economics_calc_currency_code`, persisted calculator outputs default to this (historically USD-shaped). */
export const FALLBACK_ECONOMICS_CCY = 'USD';
/** @deprecated Prefer per-line `economics_calc_currency_code` from the API. */
export const ECONOMICS_PIPELINE_CURRENCY = FALLBACK_ECONOMICS_CCY;

export function fmtMoneyWithCcy(v: number | null | undefined, currencyCode: string): string {
  if (v == null) return '—';
  return `${fmtCurrency(v)} ${currencyCode}`;
}

/** Translate a calc_flag / readiness code to a user-facing message (full text, tooltips). */
export function fmtFlag(flag: string): string {
  const labels: Record<string, string> = {
    missing_sku_assumption:
      'Controlled cost missing — add SKU assumptions in Planner defaults (not populated from DAP). Lineup DAP / local DAP / disti-reported evidence does not substitute for controlled cost.',
    missing_or_invalid_landed_cost: 'Controlled cost unavailable — verify SKU assumption or line override',
    missing_or_invalid_controlled_cost: 'Controlled cost unavailable — verify SKU assumption or line override',
    missing_distributor_term:
      'Missing distributor terms — configure on the Distributor admin page or bulk edit in Planner defaults',
    missing_customer_term:
      'Missing customer terms — configure on the Customer admin page or bulk edit in Planner defaults',
    non_positive_target_units: 'Units must be positive',
    non_positive_target_srp: 'Customer-facing list price must be positive',
    invalid_fx_rate_to_usd:
      'FX bridge invalid — plan currency units per 1 controlled-cost currency must be positive so list/campaign prices can bridge to economics outputs',
    invalid_fx_plan_currency_per_cost_currency:
      'FX bridge invalid — plan currency units per 1 controlled-cost currency must be positive so list/campaign prices can bridge to economics outputs',
    impossible_margin_stack: 'Margin stack unsustainable (margins ≥ 95%)',
    margin_floor_breach: 'Margin below floor — buy price is under controlled cost',
    reserve_breach: 'Reserve exceeds 80% of revenue',
    impossible_economics: 'Cannot compute sell-in price',
    partial_margin_stack: 'Partial margin stack — some terms defaulted to zero',
    economics_placeholder_fx_without_sku: 'FX used as placeholder without SKU economics — untrusted',
    economics_placeholder_vat_without_sku: 'VAT used as placeholder without SKU economics — untrusted',
    economics_placeholder_reserves_without_sku: 'Reserves used as placeholder without SKU economics — untrusted',
    unassigned_distributor_placeholder: 'UNASSIGNED distributor placeholder — assign a distributor for trusted channel economics',
  };
  return labels[flag] ?? flag;
}

/** Short label for Issues column chips (no raw snake_case in the cell). */
export function fmtIssueChipLabel(flag: string): string {
  const short: Record<string, string> = {
    missing_sku_assumption: 'Controlled cost missing',
    missing_or_invalid_landed_cost: 'Controlled cost unavailable',
    missing_or_invalid_controlled_cost: 'Controlled cost unavailable',
    missing_distributor_term: 'Missing distributor terms',
    missing_customer_term: 'Missing customer terms',
    non_positive_target_units: 'Invalid units',
    non_positive_target_srp: 'Invalid list price',
    invalid_fx_rate_to_usd: 'Invalid FX bridge',
    invalid_fx_plan_currency_per_cost_currency: 'Invalid FX bridge',
    impossible_margin_stack: 'Unsustainable margin stack',
    margin_floor_breach: 'Margin below floor',
    reserve_breach: 'Reserve breach',
    impossible_economics: 'Cannot compute sell-in',
    partial_margin_stack: 'Partial margin stack',
    economics_placeholder_fx_without_sku: 'FX placeholder without SKU economics',
    economics_placeholder_vat_without_sku: 'VAT placeholder without SKU economics',
    economics_placeholder_reserves_without_sku: 'Reserve placeholder without SKU economics',
    unassigned_distributor_placeholder: 'UNASSIGNED distributor — review before trusting',
  };
  return short[flag] ?? (flag.includes('_') ? flag.replace(/_/g, ' ') : flag);
}

/** True when line calc_flags indicate GP/reserve outputs must not be trusted as complete economics. */
export function lineHasBlockingEconomicsFlags(line: { calc_flags?: string[] } | null | undefined): boolean {
  if (!line?.calc_flags?.length) return false;
  return line.calc_flags.some((f) => BLOCKING_ECONOMICS_FLAGS.has(f));
}

export function roundPlannerUnits(n: number): number {
  return Math.round(Number(n));
}

/** Sum month_split_json values for lineup-derived default units (read-only). */
export function monthSplitTotalUnits(m: Record<string, number> | null | undefined): number | null {
  if (!m || typeof m !== 'object') return null;
  let t = 0;
  for (const v of Object.values(m)) {
    const n = Number(v);
    if (Number.isFinite(n)) t += n;
  }
  return t > 0 ? t : null;
}

/** Model / sales model for grid and detail (read-only from DimProduct). */
export function fmtModelSalesModel(line: {
  product_model_name?: string | null;
  product_sales_model_name?: string | null;
}): string {
  const m = line.product_model_name?.trim();
  const s = line.product_sales_model_name?.trim();
  if (m && s && m !== s) return `${m} / ${s}`;
  return m || s || '—';
}

/** Tooltip text when GP/reserve cells are blocked by readiness flags. */
export function economicsBlockingTooltip(line: { calc_flags?: string[] } | undefined): string | undefined {
  if (!line || !lineHasBlockingEconomicsFlags(line)) return undefined;
  const msgs = (line.calc_flags ?? [])
    .filter((f) => BLOCKING_ECONOMICS_FLAGS.has(f))
    .map((f) => fmtFlag(f));
  return msgs.length ? msgs.join(' · ') : 'Economics blocked — see Issues column.';
}

/** Human-readable label for a suggestion type. */
export function sugTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    target_units: 'Suggested units',
    pricing_band: 'Pricing anchor',
    promo_mix_pct: 'Promo split',
  };
  return labels[type] ?? type;
}
