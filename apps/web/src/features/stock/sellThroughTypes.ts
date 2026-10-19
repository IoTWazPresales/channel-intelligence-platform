import type { SellThroughGrain, SellThroughPreset, VatBasis } from './sellThroughFilters';

export type CoverageStatus = 'received' | 'partial' | 'due' | 'missing' | 'not_expected' | 'future';

export type SellThroughFilterOptions = {
  customers: Array<{
    id: number;
    name: string;
    code: string | null;
    reports_expected: boolean;
    has_data: boolean;
    first_period: string | null;
    last_period: string | null;
  }>;
  business_units: string[];
  categories: string[];
  series: string[];
  first_period: string | null;
  last_period: string | null;
  presets: SellThroughPreset[];
  today: string;
  calendar: { type: string; year: { label: string; start: string; end: string } };
  vat: VatBasis;
  vat_rate_pct: number;
  dimensions?: Array<{ key: string; label: string; group: string; values: string[] }>;
  max_dimensions?: number;
};

export type ProblemReason = 'out_of_stock' | 'needs_replen' | 'dropped' | 'aged' | 'stopped';

export type ProblemRow = {
  reason: ProblemReason;
  reason_label: string;
  detail: string;
  customer_id: number;
  customer_name: string;
  product_id: number;
  product: string;
  sku: string | null;
  business_unit: string | null;
  category: string | null;
  lifecycle: string | null;
  stock_on_hand: number | null;
  stock_date: string | null;
  stock_age_days: number | null;
  stock_sites: Array<{ site: string; soh: number }>;
  on_order: number | null;
  rate_recent: number;
  rate_before: number;
  weeks_of_cover: number | null;
  weeks_since_sale: number | null;
  suggested_qty: number | null;
  forward_weeks_of_cover?: number | null;
  promo_units_ahead?: number | null;
  inbound_units?: number | null;
  /** What existing data shows about this row, with evidence (Warren 2026-10-19). */
  causes?: Array<{ key: string; label: string; detail: string }>;
  /** Checks that could not run because the data is not loaded. */
  not_checked?: string[];
  judged_to: string;
  weekly_units: number[];
};

export type TrendPoint = {
  grain: SellThroughGrain;
  start: string;
  end: string;
  label: string;
  units: number;
  value: number;
  by_customer: Record<string, number>;
  compare_units?: number;
  compare_value?: number;
  compare_label?: string;
  /** Customers selling in this view that have not reported up to this period's end. */
  incomplete_customers?: string[];
};

export type SellThroughOverview = {
  filters: {
    date_from: string;
    date_to: string;
    grain: SellThroughGrain;
    compare: 'none' | 'prior_period' | 'prior_year';
    compare_from: string | null;
    compare_to: string | null;
    vat: VatBasis;
    vat_rate_pct: number;
  };
  calendar: { type: string; label: string };
  kpis: {
    units: number;
    value: number;
    value_estimated: number;
    units_without_price: number;
    compare_units: number | null;
    compare_value: number | null;
    compare_partial?: boolean;
    units_change_pct: number | null;
    value_change_pct: number | null;
    value_comparable?: boolean;
    stock_on_hand: number | null;
    stock_customers: number;
    stock_old_customers?: number;
    stock_ages?: Array<{ customer_id: number; name: string; stock_date: string; age_days: number; units: number; selling: boolean }>;
    weekly_rate: number;
    weeks_of_cover: number | null;
    skus_selling: number;
    needs_replen: number;
    out_of_stock: number;
    aged: number;
  };
  trend: TrendPoint[];
  quarters: Array<{
    label: string;
    start: string;
    end: string;
    units: number;
    value: number;
    last_year_units: number;
    last_year_value: number;
    change_pct: number | null;
    partial: boolean;
  }>;
  top_sellers: Array<{
    product_id: number;
    label: string;
    sku: string | null;
    units: number;
    value: number;
    customers: number;
    compare_units: number | null;
    change_pct: number | null;
  }>;
  customer_split: Array<{ customer_id: number; name: string; units: number }>;
  coverage: {
    grain: 'week' | 'month';
    columns: Array<{ start: string; end: string; label: string }>;
    customers: Array<{
      customer_id: number;
      name: string;
      code: string | null;
      reports_expected: boolean;
      cadence: string;
      last_reported_day: string | null;
      days_since_last: number | null;
      cells: Array<{ start: string; status: CoverageStatus; ratio: number | null }>;
      missing: number;
      partial: number;
    }>;
    missing_cells: number;
    customers_missing: string[];
  };
  problems: {
    counts: Partial<Record<ProblemReason, number>>;
    rows: ProblemRow[];
    total: number;
    rules: Record<string, number>;
  };
  notes: string[];
  summary: string[];
};
