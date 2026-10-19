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
  businessUnits: string[];
  categories: string[];
  series: string[];
};

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
    businessUnits: list(search.get('bu')),
    categories: list(search.get('category')),
    series: list(search.get('series')),
  };
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
  if (f.businessUnits.length) p.set('bu', f.businessUnits.join('|'));
  if (f.categories.length) p.set('category', f.categories.join('|'));
  if (f.series.length) p.set('series', f.series.join('|'));
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
  if (f.businessUnits.length) p.set('business_units', f.businessUnits.join('|'));
  if (f.categories.length) p.set('categories', f.categories.join('|'));
  if (f.series.length) p.set('series', f.series.join('|'));
  return p.toString();
}

/** Day grain is refused by the API past 120 days; offer only grains that fit the window. */
export function grainsFor(w: { dateFrom: string; dateTo: string } | null): SellThroughGrain[] {
  if (!w) return GRAINS;
  const days = (Date.parse(w.dateTo) - Date.parse(w.dateFrom)) / 86_400_000;
  return GRAINS.filter((g) => !(g === 'day' && days > 120));
}
