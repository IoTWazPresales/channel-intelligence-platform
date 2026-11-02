/**
 * GOV-008 independent review probes (2026-11-02), N-0114 / N-0116 chart and widget behaviour.
 * jsdom only: these assert DOM structure and data order, never pixels. Runs with
 * vitest.probe.config.mjs from apps/web. Globals (describe/it/expect/vi) come from the config.
 */
import { fireEvent, screen, within } from '@testing-library/react';
import { cloneElement, type ReactElement } from 'react';

import { builderCatalog as catalog } from '@/design-lab/fixtures/builder';
import { renderWithProviders } from '@/test-utils/renderWithProviders';
import { ComparisonChart } from '@/features/dashboards/builder/ComparisonChart';
import { V2WidgetBody } from '@/features/dashboards/builder/V2WidgetBody';
import { definitionMeasures } from '@/features/dashboards/builder/catalog';
import { tableCols, toCsv } from '@/features/dashboards/builder/table';

vi.mock('recharts', async (original) => ({
  ...(await original<typeof import('recharts')>()),
  ResponsiveContainer: ({ children }: { children: ReactElement<{ width?: number; height?: number }> }) => (
    <div>{cloneElement(children, { width: 640, height: 320 })}</div>
  ),
}));
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: Array<Record<string, unknown>> }) => (
    <div data-testid="grid-boundary">{rowData.map((r) => String(r.customer_name)).join('|')}</div>
  ),
}));

const M = 'cpor.support_usd';
const R = 'cpor.delivery_rate';
const custCol = { id: 'customer', kind: 'breakdown', label: 'Customer', fields: ['customer_id', 'customer_name'] };
const usdCol = { id: M, kind: 'measure', label: 'Support USD', fields: [M], unit: 'usd' };
const rateCol = { id: R, kind: 'measure', label: 'Delivery rate', fields: [R], unit: 'ratio' };

function hiddenRows(root: HTMLElement): string[] {
  const t = root.querySelector('table');
  if (!t) return [];
  return Array.from(t.querySelectorAll('tbody tr')).map((tr) => tr.children[0]?.textContent ?? '');
}

const LONG = (i: number) => `Kestrel Home and Garden Superstores Region ${String(i).padStart(2, '0')}`;

describe('P1 comparison over categories (ComparisonChart)', () => {
  const names = ['Alpha', 'Bravo', 'Charlie'];
  const vals = [10, 50, 30];
  const def = { v: 1, query: { measures: [M], breakdowns: ['customer'] }, display: { compare: true } } as never;
  const response = {
    ok: true,
    columns: [custCol, usdCol, { id: '__previous_m0', kind: 'measure', label: 'Support USD, previous period', fields: ['__previous_m0'], unit: 'usd' }],
    rows: names.map((n, i) => ({ customer_id: i + 1, customer_name: n, [M]: vals[i], __previous_m0: vals[i] - 1 })),
    totals: {}, truncated: false, refusals: [],
  } as never;

  it('P1a default "Highest first" orders categories by current value (expect Bravo, Charlie, Alpha)', () => {
    const { container } = renderWithProviders(
      <ComparisonChart response={response} def={def} measures={definitionMeasures(catalog, def)} catalog={catalog} visual="bar" label="previous period" height={240} />,
    );
    const order = hiddenRows(container);
    // Recorded, not asserted as pass/fail of the product: the probe prints what it observed.
    console.log('P1a observed order', JSON.stringify(order));
    expect(order).toEqual(['Bravo', 'Charlie', 'Alpha']);
  });

  it('P1b twelve long categories: top-N trims bars but how many legend entries remain?', () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({ customer_id: i + 1, customer_name: LONG(i + 1), [M]: (i + 1) * 100, __previous_m0: (i + 1) * 90 }));
    const r12 = { ...(response as object), rows } as never;
    const { container } = renderWithProviders(
      <ComparisonChart response={r12} def={def} measures={definitionMeasures(catalog, def)} catalog={catalog} visual="bar" label="previous period" height={240} />,
    );
    const shown = hiddenRows(container).length;
    const legend = container.querySelectorAll('[data-testid="chart-legend"] li').length;
    const ticks = container.querySelectorAll('[data-testid="chart-category-tick"]').length;
    const leftTicks = container.querySelectorAll('.recharts-yAxis [data-testid="chart-category-tick"]').length;
    console.log('P1b rows shown', shown, 'legend entries', legend, 'category ticks', ticks, 'left (horizontal) ticks', leftTicks);
    expect(shown).toBe(10);
    expect(ticks).toBeGreaterThan(0);
    expect(legend).toBe(shown * 2);
  });
});

describe('P2 saved presentation reaches the live chart (F-UX-02 re-check)', () => {
  const rows = Array.from({ length: 12 }, (_, i) => ({ customer_id: i + 1, customer_name: `Cust ${String.fromCharCode(76 - i)}`, [M]: (((i * 7) % 12) + 1) * 10 }));
  const result = { ok: true, columns: [custCol, usdCol], rows, totals: {}, truncated: false, refusals: [] } as never;

  it('P2a bar with display.top_n=5 shows 5 of 12', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'] }, display: { top_n: 5 } } as never;
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual="bar" catalog={catalog} result={result} loading={false} error={null} testKey="p2a" />);
    expect(hiddenRows(container)).toHaveLength(5);
    expect(screen.getByText('Top 5 of 12')).toBeInTheDocument();
  });

  it('P2b hbar with saved query sort name asc starts A-Z', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'], sort: { by: 'customer', dir: 'asc' } }, display: { top_n: 5 } } as never;
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual="hbar" catalog={catalog} result={result} loading={false} error={null} testKey="p2b" />);
    expect(hiddenRows(container)).toEqual(['Cust A', 'Cust B', 'Cust C', 'Cust D', 'Cust E']);
  });

  it('P2c saved sort name DESC: data order vs the label the Sort menu shows', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'], sort: { by: 'customer', dir: 'desc' } }, display: { top_n: 5 } } as never;
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual="bar" catalog={catalog} result={result} loading={false} error={null} testKey="p2c" />);
    const order = hiddenRows(container);
    const label = screen.getByRole('combobox', { name: 'Sort' }).textContent;
    console.log('P2c order', JSON.stringify(order), 'menu label', label);
    expect(order[0]).toBe('Cust L');
    expect(label).not.toBe('Name A–Z');
  });

  it('P2d table widget with saved query sort name asc: initial order and menu', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'], sort: { by: 'customer', dir: 'asc' } } } as never;
    renderWithProviders(<V2WidgetBody def={def} visual="table" catalog={catalog} result={result} loading={false} error={null} testKey="p2d" />);
    const grid = screen.getByTestId('grid-boundary').textContent ?? '';
    const label = screen.getByRole('combobox', { name: 'Sort' }).textContent;
    console.log('P2d table order', grid, 'menu label', label);
    expect(grid.startsWith('Cust A|Cust B')).toBe(true);
  });
});

describe('P2e/f editor default vs renderer default', () => {
  const rows = Array.from({ length: 60 }, (_, i) => ({ customer_id: i + 1, customer_name: `Cust ${i + 1}`, [M]: (i + 1) * 10 }));
  const result = { ok: true, columns: [custCol, usdCol], rows, totals: {}, truncated: false, refusals: [] } as never;
  it('P2e bar saved without top_n (editor shows "Start with top 15")', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'] } } as never;
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual="bar" catalog={catalog} result={result} loading={false} error={null} testKey="p2e" />);
    console.log('P2e rows shown', hiddenRows(container).length);
    expect(hiddenRows(container)).toHaveLength(15);
  });
  it('P2f bar saved with editor option 50: rows shown and pressed toggle', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'] }, display: { top_n: 50 } } as never;
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual="bar" catalog={catalog} result={result} loading={false} error={null} testKey="p2f" />);
    const pressed = Array.from(container.querySelectorAll('[aria-pressed="true"]')).map((b) => b.getAttribute('aria-label'));
    console.log('P2f rows shown', hiddenRows(container).length, 'pressed', JSON.stringify(pressed));
    expect(hiddenRows(container)).toHaveLength(50);
  });
});

describe('P3 two measures over a category, and dual axis, with long names (F-UX-01 re-check)', () => {
  const rows = Array.from({ length: 12 }, (_, i) => ({ customer_id: i + 1, customer_name: LONG(i + 1), [M]: (i + 1) * 100, [R]: 0.5 + i / 100 }));
  const result = { ok: true, columns: [custCol, usdCol, rateCol], rows, totals: {}, truncated: false, refusals: [] } as never;

  it.each(['bar', 'combo'] as const)('P3a two same-unit measures (%s) over customers: wrapped category ticks, controls, orientation', (visual) => {
    const E = 'cpor.estimate_units';
    const U = 'cpor.result_units';
    const cols = [custCol, { id: E, kind: 'measure', label: 'Estimated units', fields: [E], unit: 'units' }, { id: U, kind: 'measure', label: 'Result units', fields: [U], unit: 'units' }];
    const rws = Array.from({ length: 12 }, (_, i) => ({ customer_id: i + 1, customer_name: LONG(i + 1), [E]: (i + 1) * 100, [U]: (i + 1) * 80 }));
    const res = { ok: true, columns: cols, rows: rws, totals: {}, truncated: false, refusals: [] } as never;
    const def = { v: 1, query: { measures: [E, U], breakdowns: ['customer'] } } as never;
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual={visual} catalog={catalog} result={res} loading={false} error={null} testKey="p3a" />);
    const ticks = container.querySelectorAll('[data-testid="chart-category-tick"]').length;
    const leftTicks = container.querySelectorAll('.recharts-yAxis [data-testid="chart-category-tick"]').length;
    const sort = screen.queryByRole('combobox', { name: 'Sort' });
    console.log('P3a ticks', ticks, 'left', leftTicks, 'sort control', Boolean(sort));
    expect(ticks).toBe(10);
    expect(sort).not.toBeNull();
  });

  it('P3b dual-axis over customers: are category names wrapped and every category labelled?', () => {
    const def = { v: 1, query: { measures: [M, R], breakdowns: ['customer'] } } as never;
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual="dual_axis" catalog={catalog} result={result} loading={false} error={null} testKey="p3b" />);
    const wrapped = container.querySelectorAll('[data-testid="chart-category-tick"]').length;
    const xTicks = Array.from(container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')).map((t) => t.textContent);
    const sort = screen.queryByRole('combobox', { name: 'Sort' });
    console.log('P3b wrapped ticks', wrapped, 'x tick labels drawn', xTicks.length, JSON.stringify(xTicks), 'sort control', Boolean(sort));
    expect(wrapped).toBeGreaterThan(0);
    expect(xTicks.length).toBe(12);
  });
});

describe('P4 keyboard equivalents (F-UX-04 re-check)', () => {
  const rows = Array.from({ length: 4 }, (_, i) => ({ customer_id: i + 1, customer_name: `Cust ${i + 1}`, [M]: (i + 1) * 10 }));
  const result = { ok: true, columns: [custCol, usdCol], rows, totals: {}, truncated: false, refusals: [] } as never;
  it.each(['bar', 'hbar'] as const)('P4 %s: a keyboard button filters the category and Ctrl adds', (visual) => {
    const onSelect = vi.fn();
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'] } } as never;
    renderWithProviders(<V2WidgetBody def={def} visual={visual} catalog={catalog} result={result} loading={false} error={null} testKey={`p4${visual}`} onSelect={onSelect} />);
    const btn = screen.getByRole('button', { name: 'Filter by Cust 2' });
    btn.focus();
    fireEvent.click(btn, { ctrlKey: true });
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ breakdown: 'customer', value: 2 }), true);
  });
});

describe('P5 CSV export', () => {
  it('P5a ratio column: header unit vs exported raw value', () => {
    const resp = {
      ok: true, columns: [custCol, rateCol, usdCol],
      rows: [
        { customer_id: 1, customer_name: '=cmd|"/c calc"!A1', [R]: 0.86, [M]: -1234.5 },
        { customer_id: 2, customer_name: ' =1+1', [R]: 0.5, [M]: 1e21 },
        { customer_id: 3, customer_name: '＝1+1', [R]: null, [M]: 0.1 + 0.2 },
        { customer_id: 4, customer_name: 'Line1\nLine2', [R]: 1, [M]: '1234.50' },
        { customer_id: 5, customer_name: ' =SUM(A1)', [R]: 0, [M]: Number.NaN },
      ],
      totals: {}, truncated: false, refusals: [],
    } as never;
    const csv = toCsv(tableCols(resp), (resp as { rows: never[] }).rows);
    console.log('P5a csv\n' + JSON.stringify(csv));
    const lines = csv.slice(1).split('\r\n');
    expect(lines[0]).toContain('Delivery rate (%)');
    expect(lines[1]).toContain(',0.86,');
  });

  it('P5b attribute text (codes) in CSV: raw or display-cased?', () => {
    const attr = { id: 'product_line', kind: 'breakdown', label: 'Product line', fields: ['product_line'] };
    const resp = { ok: true, columns: [attr, usdCol], rows: ['UX3405MA', 'TUF GAMING', 'ACBU', 'ROG'].map((v) => ({ product_line: v, [M]: 1 })), totals: {}, truncated: false, refusals: [] } as never;
    const csv = toCsv(tableCols(resp), (resp as { rows: never[] }).rows);
    console.log('P5b csv ' + JSON.stringify(csv));
    expect(csv).toContain('UX3405MA');
  });
});
