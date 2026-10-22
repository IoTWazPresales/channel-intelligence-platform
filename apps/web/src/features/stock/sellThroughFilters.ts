/**
 * Sell-through tab filters (Warren 2026-10-19). One filter bar drives the whole page and lives in
 * the address, so a view can be bookmarked or shared and the browser Back button works.
 */

export type SellThroughGrain = 'day' | 'week' | 'month' | 'quarter';
export type SellThroughCompare = 'none' | 'prior_period' | 'prior_year';
export type VatBasis = 'ex_vat' | 'inc_vat';

export type SellThroughPreset = { key: string; label: string; date_from: string; date_to: string; grain: SellThroughGrain };

export type SellThroughFilterState = {
  preset: string | null;
  dateFrom: string | null;
  dateTo: string | null;
  grain: SellThroughGrain | null;
  compare: SellThroughCompare;
  vat: VatBasis | null;
  customers: number[];
  /** One SKU (Warren 2026-10-19: the Product box picks a single SKU; groups are added filters). */
  product: { id: number; label: string } | null;
  /** Added filters in the order added: key (prod:/spec:/cust:/site) → picked values. */
  dims: Array<{ key: string; values: string[] }>;
};

/** Address parameters for added filters: ``f.<key>=<value>``, repeated; an empty value keeps an added filter with nothing picked. */
const DIM_PREFIX = 'f.';
const LEGACY_GROUPS: Array<[string, string]> = [
  ['bu', 'prod:business_unit'],
  ['category', 'prod:category'],
  ['series', 'prod:series_name'],
];

export const DEFAULT_PRESET = 'last_13_weeks';
const GRAINS: SellThroughGrain[] = ['day', 'week', 'month', 'quarter'];
const COMPARES: SellThroughCompare[] = ['none', 'prior_period', 'prior_year'];

const list = (raw: string | null) => (raw ?? '').split('|').map((s) => s.trim()).filter(Boolean);

export function readFilters(search: URLSearchParams): SellThroughFilterState {
  const grain = search.get('grain') as SellThroughGrain | null;
  const compare = search.get('compare') as SellThroughCompare | null;
  const vat = search.get('vat');
  return {
    preset: search.get('period') ?? (search.get('from') ? null : DEFAULT_PRESET),
    dateFrom: search.get('from'),
    dateTo: search.get('to'),
    grain: grain && GRAINS.includes(grain) ? grain : null,
    compare: compare && COMPARES.includes(compare) ? compare : 'prior_year',
    vat: vat === 'ex_vat' || vat === 'inc_vat' ? vat : null,
    customers: (search.get('customers') ?? '')
      .split(',')
      .map((s) => Number(s))
      .filter((n) => Number.isInteger(n) && n > 0),
    product: Number(search.get('product')) > 0 ? { id: Number(search.get('product')), label: search.get('pl') ?? `Product ${search.get('product')}` } : null,
    dims: readDims(search),
  };
}

function readDims(search: URLSearchParams): SellThroughFilterState['dims'] {
  const out: SellThroughFilterState['dims'] = [];
  const seen = new Map<string, string[]>();
  for (const [k, v] of search.entries()) {
    if (!k.startsWith(DIM_PREFIX)) continue;
    const key = k.slice(DIM_PREFIX.length);
    if (!/^(prod|spec|cust):.+|^site$/.test(key)) continue; // a malformed link adds no filter
    if (!seen.has(key)) {
      seen.set(key, []);
      out.push({ key, values: seen.get(key)! });
    }
    if (v.trim()) seen.get(key)!.push(v);
  }
  // Links written before addable filters (bu=NB|Gaming) still work.
  for (const [param, key] of LEGACY_GROUPS) {
    const vals = list(search.get(param));
    if (vals.length && !seen.has(key)) out.push({ key, values: vals });
  }
  return out;
}

export function writeFilters(f: SellThroughFilterState): URLSearchParams {
  const p = new URLSearchParams();
  if (f.preset) p.set('period', f.preset);
  else {
    if (f.dateFrom) p.set('from', f.dateFrom);
    if (f.dateTo) p.set('to', f.dateTo);
  }
  if (f.grain) p.set('grain', f.grain);
  if (f.compare !== 'prior_year') p.set('compare', f.compare);
  if (f.vat) p.set('vat', f.vat);
  if (f.customers.length) p.set('customers', f.customers.join(','));
  if (f.product) {
    p.set('product', String(f.product.id));
    p.set('pl', f.product.label);
  }
  for (const d of f.dims) {
    if (!d.values.length) p.append(`${DIM_PREFIX}${d.key}`, '');
    for (const v of d.values) p.append(`${DIM_PREFIX}${d.key}`, v);
  }
  return p;
}

/** The window and grain the page asks for: a preset's dates, or the custom dates. */
export function resolveWindow(
  f: SellThroughFilterState,
  presets: SellThroughPreset[],
): { dateFrom: string; dateTo: string; grain: SellThroughGrain } | null {
  const preset = f.preset ? presets.find((p) => p.key === f.preset) ?? presets.find((p) => p.key === DEFAULT_PRESET) : null;
  if (preset) return { dateFrom: preset.date_from, dateTo: preset.date_to, grain: f.grain ?? preset.grain };
  if (f.dateFrom && f.dateTo && f.dateFrom <= f.dateTo) {
    const days = (Date.parse(f.dateTo) - Date.parse(f.dateFrom)) / 86_400_000;
    return { dateFrom: f.dateFrom, dateTo: f.dateTo, grain: f.grain ?? (days > 200 ? 'month' : days > 45 ? 'week' : 'day') };
  }
  const fallback = presets.find((p) => p.key === DEFAULT_PRESET) ?? presets[0];
  return fallback ? { dateFrom: fallback.date_from, dateTo: fallback.date_to, grain: f.grain ?? fallback.grain } : null;
}

export function overviewQuery(
  f: SellThroughFilterState,
  w: { dateFrom: string; dateTo: string; grain: SellThroughGrain },
): string {
  const p = new URLSearchParams({ date_from: w.dateFrom, date_to: w.dateTo, grain: w.grain, compare: f.compare });
  if (f.vat) p.set('vat', f.vat);
  if (f.customers.length) p.set('customer_ids', f.customers.join(','));
  if (f.product) p.set('product_ids', String(f.product.id));
  for (const d of f.dims) for (const v of d.values) p.append(`${DIM_PREFIX}${d.key}`, v);
  return p.toString();
}

/** Day grain is refused by the API past 120 days; offer only grains that fit the window. */
export function grainsFor(w: { dateFrom: string; dateTo: string } | null): SellThroughGrain[] {
  if (!w) return GRAINS;
  const days = (Date.parse(w.dateTo) - Date.parse(w.dateFrom)) / 86_400_000;
  return GRAINS.filter((g) => !(g === 'day' && days > 120));
}

/** Names the customers still to report for the trailing periods, so a late file is not read as a drop. */
export function incompleteNote(trend: { label: string; incomplete_customers?: string[] }[]): string {
  const tail: { label: string; names: string[] }[] = [];
  for (let i = trend.length - 1; i >= 0; i--) {
    const names = trend[i].incomplete_customers ?? [];
    if (!names.length) break;
    tail.unshift({ label: trend[i].label, names });
  }
  if (!tail.length) return '';
  const names = Array.from(new Set(tail.flatMap((t) => t.names)));
  const span = tail.length === 1 ? tail[0].label : `${tail[0].label} to ${tail[tail.length - 1].label}`;
  return `${span} not complete: ${names.slice(0, 3).join(', ')}${names.length > 3 ? ` and ${names.length - 3} more` : ''} not reported yet.`;
}
