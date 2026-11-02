/**
 * GOV-008 review 2 Nov, N-0114 chart items (batch 3). jsdom: DOM structure and data order, never pixels.
 * The recharts container is given a fixed size and the AG Grid is replaced by its row order, as the other builder tests do.
 */
import { fireEvent, screen } from '@testing-library/react';
import { cloneElement, type ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { builderCatalog as catalog } from '@/design-lab/fixtures/builder';
import { TrendChart } from '@/features/workbench-ui/charts';
import { ChartControls, sortKey, topNOptions } from '@/features/workbench-ui/ChartControls';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { definitionMeasures } from './catalog';
import { ComparisonChart } from './ComparisonChart';
import { TopNSelect, defaultTopN } from './TopNSelect';
import { V2WidgetBody } from './V2WidgetBody';

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
const LONG = (i: number) => `Kestrel Home and Garden Superstores Region ${String(i).padStart(2, '0')}`;

/** The hidden data table of a chart lists the rows it plots, in plotted order. */
function plotted(root: HTMLElement): string[] {
  const t = root.querySelector('table');
  return t ? Array.from(t.querySelectorAll('tbody tr')).map((tr) => tr.children[0]?.textContent ?? '') : [];
}

describe('comparison chart over categories', () => {
  const def = { v: 1, query: { measures: [M], breakdowns: ['customer'] }, display: { compare: true } } as never;
  const columns = [custCol, usdCol, { id: '__previous_m0', kind: 'measure', label: 'Support USD, previous period', fields: ['__previous_m0'], unit: 'usd' }];
  const respond = (rows: unknown[]) => ({ ok: true, columns, rows, totals: {}, truncated: false, refusals: [] }) as never;
  const render = (response: never) =>
    renderWithProviders(<ComparisonChart response={response} def={def} measures={definitionMeasures(catalog, def)} catalog={catalog} visual="bar" label="previous period" height={240} />);

  it('starts highest first, by each category\'s own current figure', () => {
    const names = ['Alpha', 'Bravo', 'Charlie'];
    const vals = [10, 50, 30];
    const { container } = render(respond(names.map((n, i) => ({ customer_id: i + 1, customer_name: n, [M]: vals[i], __previous_m0: vals[i] - 1 }))));
    expect(plotted(container)).toEqual(['Bravo', 'Charlie', 'Alpha']); // before: as listed
    const ticks = Array.from(container.querySelectorAll('[data-testid="chart-category-tick"] title')).map((t) => t.textContent ?? '');
    expect(ticks).toEqual(['Bravo', 'Charlie', 'Alpha']); // the axis names the categories, not their keys
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveTextContent('Highest first');
  });

  it('10 bars show a two-entry legend (current, previous), never one entry per category', () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({ customer_id: i + 1, customer_name: LONG(i + 1), [M]: (i + 1) * 100, __previous_m0: (i + 1) * 90 }));
    const { container } = render(respond(rows));
    expect(plotted(container)).toHaveLength(10);
    const legend = Array.from(container.querySelectorAll('[data-testid="chart-legend"] li')).map((li) => li.textContent ?? '');
    expect(legend).toEqual(['Support USD', 'Support USD, previous period']); // before: 24 entries, each naming a category
  });

  it('a larger top N changes the bars, not the legend', () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({ customer_id: i + 1, customer_name: LONG(i + 1), [M]: (i + 1) * 100, __previous_m0: (i + 1) * 90 }));
    const { container } = render(respond(rows));
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(plotted(container)).toHaveLength(12);
    expect(container.querySelectorAll('[data-testid="chart-legend"] li')).toHaveLength(2);
  });
});

describe('TrendChart over categories: the legend lists only the series it plots', () => {
  const rows = Array.from({ length: 12 }, (_, i) => ({ x: `c${i}`, label: `Category ${i}`, __rank: (i + 1) * 10, ...Object.fromEntries(Array.from({ length: 12 }, (_, j) => [`s${j}`, j === i ? (i + 1) * 10 : null])) }));
  const series = Array.from({ length: 12 }, (_, j) => ({ key: `s${j}`, label: `Series for category ${j}`, kind: 'bar' as const }));

  it('shows 5 legend entries for the top 5 of 12, and all 12 after "Show all"', () => {
    const { container } = renderWithProviders(
      <TrendChart data={rows} x="x" series={series} unit="units" xAxisTitle="Category" yAxisTitle="Units (units)" categoryAxis rankKey="__rank"
        xTickFormat={(v) => String(rows.find((r) => r.x === v)?.label ?? v)} initialControls={{ topN: 5, sort: { by: 'value', dir: 'desc' } }} />,
    );
    const legend = () => Array.from(container.querySelectorAll('[data-testid="chart-legend"] li')).map((li) => li.textContent ?? '');
    expect(legend()).toHaveLength(5); // before: 12
    expect(legend()).not.toContain('Series for category 0'); // the lowest are left out of the plot, so out of the legend
    expect(legend()).toContain('Series for category 11');
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(legend()).toHaveLength(12);
  });
});

describe('saved presentation reaches the chart and its menu', () => {
  const rows = Array.from({ length: 12 }, (_, i) => ({ customer_id: i + 1, customer_name: `Cust ${String.fromCharCode(76 - i)}`, [M]: (((i * 7) % 12) + 1) * 10 }));
  const result = { ok: true, columns: [custCol, usdCol], rows, totals: {}, truncated: false, refusals: [] } as never;
  const body = (def: unknown, visual: string, key: string) =>
    renderWithProviders(<V2WidgetBody def={def as never} visual={visual as never} catalog={catalog} result={result} loading={false} error={null} testKey={key} />);

  it('a saved Z–A name sort shows "Name Z–A" in the Sort menu', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'], sort: { by: 'customer', dir: 'desc' } }, display: { top_n: 5 } };
    const { container } = body(def, 'bar', 'zdesc');
    expect(plotted(container)[0]).toBe('Cust L');
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveTextContent('Name Z–A'); // before: "Name A–Z"
  });

  it('a saved A–Z name sort still shows "Name A–Z"', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'], sort: { by: 'customer', dir: 'asc' } }, display: { top_n: 5 } };
    const { container } = body(def, 'hbar', 'aasc');
    expect(plotted(container)).toEqual(['Cust A', 'Cust B', 'Cust C', 'Cust D', 'Cust E']);
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveTextContent('Name A–Z');
  });

  it('the table widget honours a saved name sort (A–Z and Z–A) and says so in its menu', () => {
    const asc = { v: 1, query: { measures: [M], breakdowns: ['customer'], sort: { by: 'customer', dir: 'asc' } } };
    const { unmount } = body(asc, 'table', 'tasc');
    expect(screen.getByTestId('grid-boundary').textContent?.startsWith('Cust A|Cust B')).toBe(true); // before: server order
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveTextContent('Name A–Z'); // before: "Highest first"
    unmount();
    const desc = { v: 1, query: { measures: [M], breakdowns: ['customer'], sort: { by: 'customer', dir: 'desc' } } };
    body(desc, 'table', 'tdesc');
    expect(screen.getByTestId('grid-boundary').textContent?.startsWith('Cust L|Cust K')).toBe(true);
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveTextContent('Name Z–A');
  });

  it('the table widget honours a saved lowest-first value sort and its top N', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'], sort: { by: M, dir: 'asc' } }, display: { top_n: 5 } };
    body(def, 'table', 'tlow');
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveTextContent('Lowest first');
    expect(screen.getByTestId('grid-boundary').textContent?.split('|')).toHaveLength(5);
  });

  it('a table widget with no saved sort is unchanged: highest first, top 10', () => {
    body({ v: 1, query: { measures: [M], breakdowns: ['customer'] } }, 'table', 'tdef');
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveTextContent('Highest first');
    expect(screen.getByTestId('grid-boundary').textContent?.split('|')).toHaveLength(10);
  });
});

describe('top N: one default for the editor and the chart, and a saved 50 shows as pressed', () => {
  const rows = Array.from({ length: 60 }, (_, i) => ({ customer_id: i + 1, customer_name: `Cust ${i + 1}`, [M]: (i + 1) * 10 }));
  const result = { ok: true, columns: [custCol, usdCol], rows, totals: {}, truncated: false, refusals: [] } as never;
  const body = (def: unknown, visual: string, key: string) =>
    renderWithProviders(<V2WidgetBody def={def as never} visual={visual as never} catalog={catalog} result={result} loading={false} error={null} testKey={key} />);

  it('the editor control shows the number the chart starts with', () => {
    for (const visual of ['bar', 'hbar']) {
      const def = { v: 1, query: { measures: [M], breakdowns: ['customer'] } };
      const { container, unmount } = body(def, visual, `d-${visual}`);
      const rowsShown = plotted(container).length;
      unmount();
      expect(rowsShown).toBe(defaultTopN(visual)); // bar 10, hbar 15
      const select = renderWithProviders(<TopNSelect visual={visual} value={undefined} onChange={() => undefined} />);
      expect(screen.getByRole('combobox')).toHaveTextContent(String(rowsShown)); // before: always 15
      select.unmount();
    }
    expect(defaultTopN('bar')).toBe(10);
    expect(defaultTopN('hbar')).toBe(15);
  });

  it('a saved top N of 50 draws 50 rows and the 50 button is the pressed one', () => {
    const def = { v: 1, query: { measures: [M], breakdowns: ['customer'] }, display: { top_n: 50 } };
    const { container } = body(def, 'bar', 'top50');
    expect(plotted(container)).toHaveLength(50);
    const pressed = Array.from(container.querySelectorAll('[aria-pressed="true"]')).map((b) => b.getAttribute('aria-label'));
    expect(pressed).toEqual(['Show top 50']); // before: nothing pressed
  });

  it('the standard options are unchanged when the saved value is one of them', () => {
    expect(topNOptions(10)).toEqual([5, 10, 15, 25, 'all']);
    expect(topNOptions('all')).toEqual([5, 10, 15, 25, 'all']);
    expect(topNOptions(50)).toEqual([5, 10, 15, 25, 50, 'all']);
    expect(topNOptions(7)).toEqual([5, 7, 10, 15, 25, 'all']);
  });
});

describe('sort menu key', () => {
  it('maps every saved sort to its own menu item', () => {
    expect(sortKey({ by: 'name', dir: 'asc' })).toBe('name-asc');
    expect(sortKey({ by: 'name', dir: 'desc' })).toBe('name-desc');
    expect(sortKey({ by: 'value', dir: 'asc' })).toBe('value-asc');
    expect(sortKey({ by: 'value', dir: 'desc' })).toBe('value-desc');
    expect(sortKey({ by: 'period' })).toBe('period');
  });

  it('the Sort menu offers Name Z–A', () => {
    renderWithProviders(<ChartControls value={{ topN: 10, sort: { by: 'name', dir: 'desc' } }} onChange={() => undefined} shown={10} total={12} />);
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveTextContent('Name Z–A');
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Sort' }));
    expect(screen.getByRole('option', { name: 'Name Z–A' })).toBeInTheDocument();
  });
});

describe('dual axis over categories', () => {
  const rows = Array.from({ length: 12 }, (_, i) => ({ customer_id: i + 1, customer_name: LONG(i + 1), [M]: (i + 1) * 100, [R]: 0.5 + i / 100 }));
  const result = { ok: true, columns: [custCol, usdCol, rateCol], rows, totals: {}, truncated: false, refusals: [] } as never;
  const def = { v: 1, query: { measures: [M, R], breakdowns: ['customer'] } } as never;

  it('uses the shared wrapped category tick and has the Sort and top N controls', () => {
    const { container } = renderWithProviders(<V2WidgetBody def={def} visual="dual_axis" catalog={catalog} result={result} loading={false} error={null} testKey="dual" />);
    expect(container.querySelectorAll('[data-testid="chart-category-tick"]').length).toBeGreaterThan(0); // before: 0
    expect(screen.getByRole('combobox', { name: 'Sort' })).toBeInTheDocument(); // before: none
    // The axis names the customers, not their keys ("customer:312").
    const names = Array.from(container.querySelectorAll('[data-testid="chart-category-tick"] title')).map((t) => t.textContent ?? '');
    expect(names).toContain(LONG(12));
    expect(names.some((n) => /^customer:/.test(n))).toBe(false);
    expect(screen.getByRole('button', { name: 'Show top 10' })).toHaveAttribute('aria-pressed', 'true');
    expect(plotted(container)).toHaveLength(10); // 12 categories, top 10, highest first
  });

  it('keeps both axis titles with their units', () => {
    renderWithProviders(<V2WidgetBody def={def} visual="dual_axis" catalog={catalog} result={result} loading={false} error={null} testKey="dual2" />);
    expect(screen.getByTestId('chart-axis-title-top')).toHaveTextContent(/Support USD/);
    expect(screen.getByTestId('chart-axis-title-right')).toHaveTextContent(/Delivery rate/);
  });

  it('a saved name sort and top N reach it', () => {
    const saved = { v: 1, query: { measures: [M, R], breakdowns: ['customer'], sort: { by: 'customer', dir: 'desc' } }, display: { top_n: 5 } } as never;
    const { container } = renderWithProviders(<V2WidgetBody def={saved} visual="dual_axis" catalog={catalog} result={result} loading={false} error={null} testKey="dual3" />);
    expect(plotted(container)).toEqual([LONG(12), LONG(11), LONG(10), LONG(9), LONG(8)]);
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveTextContent('Name Z–A');
  });
});
