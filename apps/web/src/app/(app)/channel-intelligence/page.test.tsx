import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import ChannelIntelligencePage from './page';

const replace = vi.fn();
let search = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => search,
  usePathname: () => '/channel-intelligence',
}));

const FILTERS = {
  customers: [
    { id: 299, name: 'Amazon', code: 'AMZ', reports_expected: true, has_data: true, first_period: '2026-01-01', last_period: '2026-10-12' },
    { id: 7, name: 'Pinnacle', code: 'PIN', reports_expected: true, has_data: false, first_period: null, last_period: null },
  ],
  business_units: ['NB'],
  categories: [],
  series: [],
  first_period: '2026-01-01',
  last_period: '2026-10-12',
  presets: [
    { key: 'last_13_weeks', label: 'Last 13 weeks', date_from: '2026-07-20', date_to: '2026-10-18', grain: 'week' },
    { key: 'year_to_date', label: '2026 to date', date_from: '2026-01-01', date_to: '2026-10-19', grain: 'month' },
  ],
  today: '2026-10-19',
  calendar: { type: 'gregorian', year: { label: '2026', start: '2026-01-01', end: '2026-12-31' } },
  vat: 'ex_vat',
  vat_rate_pct: 0.15,
  dimensions: [
    { key: 'prod:business_unit', label: 'Business unit', group: 'Product', values: ['NB'] },
    { key: 'spec:RAM', label: 'RAM', group: 'Specs', values: ['8GB', '16GB'] },
  ],
  max_dimensions: 6,
};

const OVERVIEW = {
  filters: {
    date_from: '2026-07-20',
    date_to: '2026-10-18',
    grain: 'week',
    compare: 'prior_year',
    compare_from: '2025-07-21',
    compare_to: '2025-10-19',
    vat: 'ex_vat',
    vat_rate_pct: 0.15,
  },
  calendar: { type: 'gregorian', label: '2026' },
  kpis: {
    units: 7650,
    value: 765000,
    value_estimated: 0,
    units_without_price: 0,
    compare_units: 6000,
    compare_value: 600000,
    units_change_pct: 0.275,
    value_change_pct: 0.275,
    stock_on_hand: 1200,
    stock_customers: 1,
    weekly_rate: 600,
    weeks_of_cover: 2,
    skus_selling: 63,
    needs_replen: 1,
    out_of_stock: 1,
    aged: 0,
  },
  trend: [
    { grain: 'week', start: '2026-10-12', end: '2026-10-18', label: 'W42', units: 600, value: 60000, by_customer: { '299': 600 }, compare_units: 500 },
  ],
  quarters: [{ label: '26Q4', start: '2026-10-01', end: '2026-12-31', units: 1000, value: 1, last_year_units: 800, last_year_value: 1, change_pct: 0.25, partial: true }],
  top_sellers: [{ product_id: 1, label: 'Model A (SKU-A)', sku: 'SKU-A', units: 900, value: 90000, customers: 1, compare_units: 700, change_pct: 0.28 }],
  customer_split: [{ customer_id: 299, name: 'Amazon', units: 7650 }],
  coverage: {
    grain: 'week',
    columns: [{ start: '2026-10-12', end: '2026-10-18', label: 'W42' }],
    customers: [
      { customer_id: 299, name: 'Amazon', code: 'AMZ', reports_expected: true, cadence: 'daily', last_reported_day: '2026-10-18', days_since_last: 1, cells: [{ start: '2026-10-12', status: 'received', ratio: 1 }], missing: 0, partial: 0 },
      { customer_id: 7, name: 'Pinnacle', code: 'PIN', reports_expected: true, cadence: 'weekly', last_reported_day: null, days_since_last: null, cells: [{ start: '2026-10-12', status: 'missing', ratio: 0 }], missing: 1, partial: 0 },
    ],
    missing_cells: 1,
    customers_missing: ['Pinnacle'],
  },
  problems: {
    counts: { needs_replen: 1, out_of_stock: 1 },
    rows: [
      {
        reason: 'out_of_stock', reason_label: 'Out of stock, was selling', detail: '0 in stock; was selling 5.0 a week',
        customer_id: 299, customer_name: 'Amazon', product_id: 2, product: 'Model B (SKU-B)', sku: 'SKU-B', business_unit: 'NB',
        category: null, lifecycle: null, stock_on_hand: 0, on_order: 0, rate_recent: 5, rate_before: 5, weeks_of_cover: null,
        weeks_since_sale: 0, suggested_qty: 30, judged_to: '2026-10-18', weekly_units: [5, 5, 5],
      },
      {
        reason: 'needs_replen', reason_label: 'Needs replenishing', detail: '2.0 weeks of cover (replenish below 4)',
        customer_id: 299, customer_name: 'Amazon', product_id: 1, product: 'Model A (SKU-A)', sku: 'SKU-A', business_unit: 'NB',
        category: null, lifecycle: null, stock_on_hand: 20, on_order: 0, rate_recent: 10, rate_before: 10, weeks_of_cover: 2,
        weeks_since_sale: 0, suggested_qty: 40, judged_to: '2026-10-18', weekly_units: [10, 10, 10],
        causes: [{ key: 'promo_ahead', label: 'Promotion coming', detail: 'Price promo from 2026-10-20, 80 units planned' }],
        not_checked: ['search ranking (no data source)'],
      },
    ],
    total: 2,
    rules: { no_sales_weeks: 8 },
  },
  notes: [],
  summary: ['Units sold up 28% on the same period last year (7,650 vs 6,000).', 'Reports missing in this window: Pinnacle.'],
};

const apiGet = vi.fn(async (url: string) => {
  if (url.startsWith('/api/v1/sell-through/filters')) return FILTERS;
  if (url.startsWith('/api/v1/sell-through/overview')) return OVERVIEW;
  if (url.startsWith('/api/v1/sell-through/product/1'))
    return {
      product: {
        id: 1, label: 'Model A (SKU-A)', sku: 'SKU-A', name: 'Model A', sales_model_name: 'Model A', part_number: null,
        ean: '600', upc: null, business_unit: 'NB', category: null, series: null, product_line: null, lifecycle: null,
        launch_date: null, retired_date: null, price_band: null, specs: { RAM: '16GB' },
      },
      as_of: '2026-10-18',
      vat: 'ex_vat',
      customers: [
        {
          customer_id: 299, customer_name: 'Amazon', weekly_units: [10, 10], units_26w: 20, rate_4w: 10,
          stock_on_hand: 20, stock_date: '2025-06-15', stock_age_days: 490, on_order: 0,
          stock_sites: [{ site: 'DC North', soh: 20 }], price_history: [{ period: '2026-10-12', price: 999 }], latest_price: 999,
        },
      ],
      lowest_price_customer: { customer_name: 'Amazon', price: 999 },
    };
  if (url.startsWith('/api/v1/sell-through/narrative')) return { source: 'rules', text: 'x', reason: 'AI assist is off in this installation' };
  return {};
});

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGet(url),
  safeDisplayError: (e: unknown) => String(e),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <ChannelIntelligencePage />
    </QueryClientProvider>,
  );
}

describe('Sell-through tab (Warren 2026-10-19)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    search = new URLSearchParams();
  });

  it('shows the summary, reports received, headline numbers and SKUs needing attention', async () => {
    renderPage();
    expect(await screen.findByTestId('sellthrough-overview')).toBeInTheDocument();
    expect(await screen.findByText(/Units sold up 28%/)).toBeInTheDocument();
    const strip = screen.getByTestId('sellthrough-reports-strip');
    expect(within(strip).getByText('1 up to date')).toBeInTheDocument();
    expect(within(strip).getByText('Pinnacle · nothing loaded').closest('a')).toHaveAttribute(
      'href',
      '/admin/imports?template=customer_sell_through&customer=7',
    );
    const coverage = screen.getByTestId('sellthrough-coverage');
    expect(within(coverage).getByText('Pinnacle')).toBeInTheDocument();
    expect(within(coverage).getByText('Nothing loaded')).toBeInTheDocument();
    expect(screen.getByTestId('sellthrough-kpi-units')).toHaveTextContent('7,650');
    expect(screen.getByTestId('sellthrough-problem-chip-out_of_stock')).toHaveTextContent('1');
    const overviewCall = apiGet.mock.calls.map((c) => c[0]).find((u) => u.includes('/overview?'))!;
    expect(overviewCall).toContain('date_from=2026-07-20');
    expect(overviewCall).toContain('compare=prior_year');
  });

  it('carries the customer filter from the address into the request', async () => {
    search = new URLSearchParams('customers=299&period=year_to_date');
    renderPage();
    await screen.findByTestId('sellthrough-overview');
    const overviewCall = apiGet.mock.calls.map((c) => c[0]).find((u) => u.includes('/overview?'))!;
    expect(overviewCall).toContain('customer_ids=299');
    expect(overviewCall).toContain('date_from=2026-01-01');
    expect(overviewCall).toContain('grain=month');
  });

  it('a period chip writes the choice to the address', async () => {
    renderPage();
    const presets = await screen.findByTestId('sellthrough-presets');
    await userEvent.click(within(presets).getByText('2026 to date'));
    expect(replace).toHaveBeenCalledWith('/channel-intelligence?period=year_to_date', { scroll: false });
  });

  it('adds a filter from the list and sends its picks', async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId('sellthrough-add-filter'));
    await userEvent.click(await screen.findByText('RAM'));
    expect(replace).toHaveBeenLastCalledWith('/channel-intelligence?period=last_13_weeks&f.spec%3ARAM=', { scroll: false });
  });

  it('sends added filter picks from the address to the API', async () => {
    search = new URLSearchParams('f.spec:RAM=16GB&product=9&pl=X1409VA');
    renderPage();
    expect(await screen.findByTestId('sellthrough-dim-spec:RAM')).toBeInTheDocument();
    const call = apiGet.mock.calls.map((c) => c[0]).find((u) => u.includes('/overview?'))!;
    expect(call).toContain('f.spec%3ARAM=16GB');
    expect(call).toContain('product_ids=9');
  });

  it('opens the product panel from a SKU needing attention', async () => {
    renderPage();
    const table = await screen.findByTestId('sellthrough-problems');
    await userEvent.click(await within(table).findByText('Model A (SKU-A)'));
    const panel = await screen.findByTestId('sellthrough-panel-focus');
    expect(panel).toHaveTextContent('Needs replenishing at Amazon');
    expect(await screen.findByText(/reported 2025-06-15 \(490 days old\)/)).toBeInTheDocument();
    expect(screen.getByText('Stores: DC North 20')).toBeInTheDocument();
    expect(screen.getByText('16GB')).toBeInTheDocument();
    expect(screen.getByTestId('sellthrough-panel-causes')).toHaveTextContent('Promotion coming: Price promo from 2026-10-20, 80 units planned');
    expect(screen.getByText('Not checked: search ranking (no data source).')).toBeInTheDocument();
  });

  it('says why the AI summary is not available', async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId('sellthrough-ai-summary'));
    expect(await screen.findByText(/AI summary not available: AI assist is off/)).toBeInTheDocument();
  });
});
