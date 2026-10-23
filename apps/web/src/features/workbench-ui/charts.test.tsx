import { fireEvent, screen, within } from '@testing-library/react';
import { cloneElement, type ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import {
  CategoryBars,
  ChartFigure,
  PairedBars,
  RankedBars,
  ShareChart,
  Sparkline,
  StateKey,
  TrendChart,
  axisTitle,
  chooseCategoryLayout,
  formatChartValue,
  formatMeasure,
  formatNumber,
  horizontalLabelWidth,
  niceAxis,
  rankBars,
  sparklinePoints,
  thresholdState,
  unitWord,
  wrapLabel,
  type MeasureUnit,
} from './charts';

// jsdom has no layout, so ResponsiveContainer would draw nothing: give the drawing a fixed size so
// ticks, <title> and legends render and can be asserted.
vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement<{ width?: number; height?: number }> }) => (
      <div style={{ width: 800, height: 400 }}>{cloneElement(children, { width: 800, height: 400 })}</div>
    ),
  };
});

/** Number text uses a no-break space for groups and symbol gaps; write expectations with plain spaces. */
const nb = (s: string) => s.replace(/ /g, String.fromCharCode(160));

/** Body rows of the chart's visually-hidden data table, as cell text. */
function tableRows(root: HTMLElement = document.body): string[][] {
  const table = within(root).getByRole('table');
  return within(table)
    .getAllByRole('row')
    .slice(1)
    .map((r) => Array.from(r.children).map((c) => c.textContent ?? ''));
}

describe('number and unit helpers', () => {
  it('groups thousands with a space and keeps a decimal point', () => {
    expect(formatNumber(1092)).toBe('1 092');
    expect(formatNumber(1234567.456, { digits: 1 })).toBe('1 234 567.5');
    expect(formatNumber(4.37)).toBe('4.37');
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber(Number.NaN)).toBe('—');
  });

  it('formats by unit', () => {
    expect(formatMeasure(5.4, 'weeks')).toBe('5.4');
    expect(formatMeasure(5, 'weeks', 'short')).toBe('5.0w');
    expect(formatMeasure(5.43, 'weeks', 'long')).toBe('5.4 weeks');
    expect(formatMeasure(0.862, 'percent')).toBe('86.2%');
    expect(formatMeasure(15560, 'units')).toBe('15 560');
    expect(formatMeasure(15560, 'units', 'long')).toBe('15 560 units');
    // N-0114: "US$" on charts, report tiles and headers alike (text only).
    expect(formatMeasure(1200, 'zar', 'short')).toBe(nb('R 1 200'));
    expect(formatMeasure(1200, 'usd', 'short')).toBe(nb('US$ ') + '1 200');
    expect(formatMeasure(undefined, 'units')).toBe('—');
    expect(unitWord('weeks')).toBe('weeks');
    expect(unitWord('count')).toBeNull();
  });

  it('thresholdState: red under 2, amber under 4, otherwise ok', () => {
    expect(thresholdState(1.99)).toBe('stop');
    expect(thresholdState(2)).toBe('warn');
    expect(thresholdState(3.99)).toBe('warn');
    expect(thresholdState(4)).toBe('ok');
    expect(thresholdState(null)).toBeNull();
    expect(thresholdState(5, { stop: 2, warn: 6 })).toBe('warn');
  });

  it('rankBars sorts, caps and drops rows without a value', () => {
    const data = [
      { label: 'a', value: 3 },
      { label: 'b', value: null },
      { label: 'c', value: 1 },
      { label: 'd', value: 2 },
    ];
    expect(rankBars(data, { sort: 'asc' }).shown.map((d) => d.label)).toEqual(['c', 'd', 'a']);
    expect(rankBars(data, { sort: 'desc', max: 2 })).toMatchObject({ total: 3, withoutValue: 1 });
    expect(rankBars(data, { sort: 'desc', max: 2 }).shown.map((d) => d.label)).toEqual(['a', 'd']);
    expect(rankBars(data, { sort: 'none' }).shown.map((d) => d.label)).toEqual(['a', 'c', 'd']);
  });

  it('sparklinePoints spans the box and ends at the last value', () => {
    const { points, last } = sparklinePoints([1, 3, 2], 200, 28);
    expect(points.split(' ')).toHaveLength(3);
    expect(last?.x).toBe(200);
    expect(sparklinePoints([], 200, 28).last).toBeNull();
  });

  it('niceAxis gives round ticks that cover the largest value', () => {
    expect(niceAxis(6.4)).toEqual({ max: 8, ticks: [0, 2, 4, 6, 8] });
    expect(niceAxis(15.4)).toEqual({ max: 20, ticks: [0, 5, 10, 15, 20] });
    expect(niceAxis(14028).max).toBeGreaterThanOrEqual(14028);
    expect(niceAxis(0)).toEqual({ max: 1, ticks: [0, 1] });
  });
});

describe('accessible chart output', () => {
  it('ChartFigure gives the drawing a name and a hidden data table', () => {
    renderWithProviders(
      <ChartFigure summary="Cover by distributor" table={{ caption: 'Cover', columns: ['Distributor', 'Weeks'], rows: [['A', '1.0w']] }}>
        <div />
      </ChartFigure>,
    );
    expect(screen.getByRole('img', { name: 'Cover by distributor' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Cover' });
    expect(within(table).getByRole('rowheader', { name: 'A' })).toBeInTheDocument();
    expect(within(table).getByRole('cell', { name: '1.0w' })).toBeInTheDocument();
  });

  it('RankedBars lists sorted, capped values in its data table', () => {
    renderWithProviders(
      <RankedBars
        data={[
          { label: 'Highveld', value: 6.4, tone: 'primary' },
          { label: 'Kwazulu', value: 1.8, tone: 'danger' },
          { label: 'Coastal', value: 3.6, tone: 'warning' },
          { label: 'Nobody', value: null },
        ]}
        sort="asc"
        max={2}
        threshold={{ value: 4, label: '4-week threshold' }}
        format={(v) => `${v.toFixed(1)}w`}
        summary="Weeks of cover by distributor"
        labelHeader="Distributor"
        valueHeader="Weeks of cover"
      />,
    );
    expect(screen.getByRole('img', { name: 'Weeks of cover by distributor' })).toBeInTheDocument();
    const rows = within(screen.getByRole('table')).getAllByRole('row');
    expect(rows.map((r) => r.textContent)).toEqual(['DistributorWeeks of cover', 'Kwazulu1.8w', 'Coastal3.6w']);
  });

  it('TrendChart without summary renders as before; with summary it is named', () => {
    const data = [
      { w: 'W1', v: 1 },
      { w: 'W2', v: 2 },
    ];
    const { unmount } = renderWithProviders(<TrendChart data={data} x="w" series={[{ key: 'v', label: 'V', kind: 'line' }]} />);
    expect(screen.queryByRole('img')).toBeNull();
    unmount();
    renderWithProviders(
      <TrendChart data={data} x="w" series={[{ key: 'v', label: 'V', kind: 'line' }]} lastPointLabel legend={false} summary="V by week" />,
    );
    expect(screen.getByRole('img', { name: 'V by week' })).toBeInTheDocument();
  });

  it('Sparkline and StateKey render with text alternatives', () => {
    renderWithProviders(
      <>
        <Sparkline values={[6.3, 6, 5.4]} label="12-week trend, 6.3 to 5.4 weeks" />
        <StateKey items={[{ tone: 'danger', label: 'Under 2 weeks' }]} />
      </>,
    );
    expect(screen.getByRole('img', { name: '12-week trend, 6.3 to 5.4 weeks' })).toBeInTheDocument();
    expect(screen.getByText('Under 2 weeks')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------------------------------------
 * N-0114 chart fixes
 * ---------------------------------------------------------------------------------------------- */

describe('formatChartValue', () => {
  it('zar and usd: compact ticks and labels, full grouping with the symbol in tooltips', () => {
    expect(formatChartValue(1_234_567, 'zar', 'tick')).toBe(nb('R 1.2 M'));
    expect(formatChartValue(850_000, 'zar', 'tick')).toBe(nb('R 850 k'));
    expect(formatChartValue(9_500, 'zar', 'tick')).toBe(nb('R 9 500'));
    expect(formatChartValue(1_234_567, 'zar', 'label')).toBe(nb('R 1.2 M'));
    expect(formatChartValue(1_234_567, 'zar', 'full')).toBe(nb('R 1 234 567'));
    expect(formatChartValue(12.5, 'zar', 'full')).toBe(nb('R 12.50'));
    expect(formatChartValue(1_234_567, 'usd', 'tick')).toBe(nb('US$ 1.2 M'));
    expect(formatChartValue(1_234_567, 'usd', 'label')).toBe(nb('US$ 1.2 M'));
    expect(formatChartValue(1_234_567, 'usd', 'full')).toBe(nb('US$ 1 234 567'));
  });

  it('negative values keep the sign before the symbol', () => {
    expect(formatChartValue(-1_234_567, 'zar', 'tick')).toBe(nb('-R 1.2 M'));
    expect(formatChartValue(-50, 'usd', 'full')).toBe(nb('-US$ 50.00'));
    expect(formatChartValue(-12_345, 'units', 'tick')).toBe(nb('-12.3 k'));
    expect(formatChartValue(-1_234, 'count', 'full')).toBe(nb('-1 234'));
  });

  it('units and count: bare on axes, "units" spelled out in full text', () => {
    expect(formatChartValue(1_200, 'units', 'tick')).toBe(nb('1 200'));
    expect(formatChartValue(12_345, 'units', 'label')).toBe(nb('12.3 k'));
    expect(formatChartValue(1_234, 'units', 'full')).toBe(`${nb('1 234')} units`);
    expect(formatChartValue(1_234, 'count', 'tick')).toBe(nb('1 234'));
    expect(formatChartValue(12_300, 'count', 'label')).toBe(nb('12.3 k'));
    expect(formatChartValue(1_234, 'count', 'full')).toBe(nb('1 234'));
  });

  it('compact steps at the 10 000, 1 000 000 and 1 000 000 000 boundaries', () => {
    expect(formatChartValue(9_999, 'count', 'tick')).toBe(nb('9 999'));
    expect(formatChartValue(10_000, 'count', 'tick')).toBe(nb('10 k'));
    expect(formatChartValue(99_999, 'count', 'tick')).toBe(nb('100 k'));
    expect(formatChartValue(150_000, 'count', 'tick')).toBe(nb('150 k'));
    expect(formatChartValue(999_999, 'count', 'tick')).toBe(nb('1 M'));
    expect(formatChartValue(1_000_000, 'count', 'tick')).toBe(nb('1 M'));
    expect(formatChartValue(1_240_000, 'count', 'tick')).toBe(nb('1.2 M'));
    expect(formatChartValue(2_500_000_000, 'count', 'tick')).toBe(nb('2.5 bn'));
  });

  it('percent takes ratios: whole-point ticks, one decimal in labels and full text', () => {
    expect(formatChartValue(0.86, 'percent', 'tick')).toBe('86%');
    expect(formatChartValue(0.865, 'percent', 'tick')).toBe('86.5%');
    expect(formatChartValue(0.86, 'percent', 'label')).toBe('86.0%');
    expect(formatChartValue(0.862, 'percent', 'full')).toBe('86.2%');
  });

  it('weeks, days and quarters: bare ticks, short labels, words in full text', () => {
    expect(formatChartValue(5.4, 'weeks', 'tick')).toBe('5.4');
    expect(formatChartValue(4, 'weeks', 'tick')).toBe('4');
    expect(formatChartValue(5.43, 'weeks', 'label')).toBe('5.4w');
    expect(formatChartValue(5.4, 'weeks', 'full')).toBe('5.4 weeks');
    expect(formatChartValue(12, 'days', 'tick')).toBe('12');
    expect(formatChartValue(12, 'days', 'label')).toBe('12d');
    expect(formatChartValue(12, 'days', 'full')).toBe('12 days');
    expect(formatChartValue(1.5, 'quarters', 'tick')).toBe('1.5');
    expect(formatChartValue(1.5, 'quarters', 'label')).toBe('1.5q');
    expect(formatChartValue(1.5, 'quarters', 'full')).toBe('1.5 quarters');
  });

  it('unknown unit: compact bare, two decimals in full; no value gives a dash', () => {
    expect(formatChartValue(12_345, 'number', 'tick')).toBe(nb('12.3 k'));
    expect(formatChartValue(1_234.567, 'number', 'full')).toBe(nb('1 234.57'));
    expect(formatChartValue(4.37)).toBe('4.37');
    for (const style of ['tick', 'label', 'full'] as const) {
      expect(formatChartValue(null, 'zar', style)).toBe('—');
      expect(formatChartValue(undefined, 'units', style)).toBe('—');
      expect(formatChartValue(Number.NaN, 'percent', style)).toBe('—');
      expect(formatChartValue(Number.POSITIVE_INFINITY, 'count', style)).toBe('—');
    }
  });

  it('unit words: R and US$', () => {
    expect(unitWord('zar')).toBe('R');
    expect(unitWord('usd')).toBe('US$');
  });

  it('axisTitle adds the unit unless the label already names it', () => {
    expect(axisTitle('Sales value', 'zar')).toBe('Sales value (R)');
    expect(axisTitle('Price', 'zar')).toBe('Price (R)');
    expect(axisTitle('Price (R)', 'zar')).toBe('Price (R)');
    expect(axisTitle('Support spend', 'usd')).toBe('Support spend (US$)');
    expect(axisTitle('Fill rate', 'percent')).toBe('Fill rate (%)');
    expect(axisTitle('Weeks of cover', 'weeks')).toBe('Weeks of cover');
    expect(axisTitle('Shipments', 'count')).toBe('Shipments');
    expect(axisTitle('Sell-out', undefined)).toBe('Sell-out');
  });
});

describe('long category names and layout', () => {
  const short = (n: number) => Array.from({ length: n }, (_, i) => `C${i}`);

  it('chooseCategoryLayout: over 8 categories or a label over 14 characters goes horizontal', () => {
    expect(chooseCategoryLayout(short(8))).toBe('vertical');
    expect(chooseCategoryLayout(short(9))).toBe('horizontal');
    expect(chooseCategoryLayout(['a'.repeat(14), 'b'])).toBe('vertical');
    expect(chooseCategoryLayout(['a'.repeat(15), 'b'])).toBe('horizontal');
  });

  it('chooseCategoryLayout: a time axis never flips; force wins', () => {
    expect(chooseCategoryLayout(Array.from({ length: 20 }, () => 'a'.repeat(30)), { timeAxis: true })).toBe('vertical');
    expect(chooseCategoryLayout(short(2), { force: 'horizontal' })).toBe('horizontal');
    expect(chooseCategoryLayout(short(20), { force: 'vertical' })).toBe('vertical');
  });

  it('wrapLabel breaks at words, hard-breaks long words, caps at two lines with an ellipsis', () => {
    expect(wrapLabel('Kwazulu Channel', 10)).toEqual(['Kwazulu', 'Channel']);
    expect(wrapLabel('Supercalifragilistic', 8)).toEqual(['Supercal', 'ifragil…']);
    expect(wrapLabel('Northern Cape Retail', 10)).toEqual(['Northern', 'Cape…']);
    expect(wrapLabel('Coastal', 20)).toEqual(['Coastal']);
    expect(wrapLabel('Coastal Tech Supply', 30, 1)).toEqual(['Coastal Tech Supply']);
  });

  it('horizontalLabelWidth: at least 64 px, at most 45% of the chart', () => {
    expect(horizontalLabelWidth(['ab'], 1280)).toBe(64);
    expect(horizontalLabelWidth(['a'.repeat(20)], 1280)).toBe(140);
    expect(horizontalLabelWidth(['a'.repeat(100)], 390)).toBeLessThanOrEqual(0.45 * 390);
    expect(horizontalLabelWidth(['a'.repeat(100)], 390)).toBe(175);
    expect(horizontalLabelWidth(['a'.repeat(200)], 1280)).toBe(576);
  });
});

const LONG_40 = 'Northern Cape Consolidated Retail Groups';
const LONG_60 = 'Northern Cape Consolidated Retail Holdings (Pty) Ltd, Kimber';

describe('chart rendering (N-0114)', () => {
  it('every chart renders its axis titles as text', () => {
    renderWithProviders(
      <>
        <CategoryBars data={[{ b: '0–30d', v: 10 }]} x="b" y="v" unit="zar" xAxisTitle="Age (days)" yAxisTitle="Outstanding (R)" />
        <PairedBars data={[{ q: 'Q1', a: 1, b: 2 }]} x="q" a="a" b="b" aLabel="Last year" bLabel="This year" timeAxis unit="units" xAxisTitle="Quarter" yAxisTitle="Units sold (units)" />
        <TrendChart data={[{ w: 'W1', v: 1 }]} x="w" series={[{ key: 'v', label: 'Sell-out', kind: 'line' }]} unit="units" xAxisTitle="Week" yAxisTitle="Sell-out (units)" />
        <RankedBars data={[{ label: 'North', value: 3 }]} summary="Units by customer" unit="units" xAxisTitle="Customer" yAxisTitle="Units (units)" />
      </>,
    );
    for (const t of ['Age (days)', 'Outstanding (R)', 'Quarter', 'Units sold (units)', 'Week', 'Sell-out (units)', 'Customer', 'Units (units)']) {
      expect(screen.getAllByText(t).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByTestId('chart-axis-title-top')).toHaveLength(4);
    expect(screen.getAllByTestId('chart-axis-title-bottom')).toHaveLength(4);
  });

  it('TrendChart: no legend for one series by default, a legend for two', () => {
    const data = [
      { w: 'W1', a: 1, b: 2 },
      { w: 'W2', a: 2, b: 3 },
    ];
    const { unmount } = renderWithProviders(<TrendChart data={data} x="w" series={[{ key: 'a', label: 'Sell-out', kind: 'line' }]} />);
    expect(screen.queryByTestId('chart-legend')).toBeNull();
    unmount();
    renderWithProviders(
      <TrendChart
        data={data}
        x="w"
        series={[
          { key: 'a', label: 'Sell-out', kind: 'line' },
          { key: 'b', label: 'Shipped in', kind: 'bar' },
        ]}
      />,
    );
    const legend = screen.getByTestId('chart-legend');
    expect(within(legend).getByText('Sell-out')).toBeInTheDocument();
    expect(within(legend).getByText('Shipped in')).toBeInTheDocument();
  });

  it('PairedBars never cuts a 40-character customer name; ticks carry the full name in <title>', () => {
    const { container } = renderWithProviders(
      <PairedBars
        data={[
          { customer: LONG_40, plan: 120, shipped: 80 },
          { customer: 'Coastal', plan: 60, shipped: 66 },
        ]}
        x="customer"
        a="plan"
        b="shipped"
        aLabel="Plan"
        bLabel="Shipped"
        unit="units"
        xAxisTitle="Customer"
        yAxisTitle="Units, plan and shipped (units)"
      />,
    );
    const ticks = Array.from(container.querySelectorAll('[data-testid="chart-category-tick"]'));
    expect(ticks.length).toBe(2);
    expect(ticks.map((t) => t.textContent ?? '').join(' ')).not.toContain('…');
    expect(ticks.map((t) => t.querySelector('title')?.textContent)).toContain(LONG_40);
    expect(within(screen.getByTestId('chart-legend')).getByText('Plan')).toBeInTheDocument();
  });

  it('CategoryTick keeps the full name in <title> even when the label is wrapped', () => {
    // Seven categories in a 640 px chart: about 80 px per band, so the long name wraps to two lines.
    const data = [LONG_60, ...Array.from({ length: 6 }, (_, i) => `Retailer ${i + 2}`)].map((name, i) => ({ name, v: i + 1 }));
    const { container } = renderWithProviders(
      <CategoryBars data={data} x="name" y="v" layout="vertical" controls={false} xAxisTitle="Customer" yAxisTitle="Value" />,
    );
    const tick = container.querySelector('[data-testid="chart-category-tick"]');
    expect(tick?.querySelector('title')?.textContent).toBe(LONG_60);
    expect(tick?.querySelectorAll('tspan').length).toBe(2);
  });

  it('RankedBars says how many rows are shown: "Top 10 of 37"', () => {
    const data = Array.from({ length: 37 }, (_, i) => ({ label: `Customer ${i + 1}`, value: i + 1 }));
    renderWithProviders(<RankedBars data={data} summary="Units by customer" unit="units" xAxisTitle="Customer" yAxisTitle="Units (units)" />);
    expect(screen.getByText('Top 10 of 37')).toBeInTheDocument();
    expect(tableRows()).toHaveLength(10);
  });

  it('ChartControls change the count shown and the order', () => {
    const data = Array.from({ length: 37 }, (_, i) => ({ label: `Customer ${i + 1}`, value: i + 1 }));
    renderWithProviders(<RankedBars data={data} summary="Units by customer" unit="units" xAxisTitle="Customer" yAxisTitle="Units (units)" />);
    expect(tableRows()[0][0]).toBe('Customer 37');
    fireEvent.click(screen.getByRole('button', { name: 'Show top 5' }));
    expect(tableRows()).toHaveLength(5);
    expect(screen.getByText('Top 5 of 37')).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Sort' }));
    fireEvent.click(screen.getByRole('option', { name: 'Name A–Z' }));
    expect(tableRows().map((r) => r[0])).toEqual(['Customer 1', 'Customer 2', 'Customer 3', 'Customer 4', 'Customer 5']);
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(tableRows()).toHaveLength(37);
    expect(screen.queryByText(/Top \d+ of 37/)).toBeNull();
  });

  it('ShareChart legend shows the full 60-character name and shares of the full total', () => {
    const values = [300, 200, 100, 80, 70, 60, 50, 40, 40, 30, 20, 10]; // sums to 1 000
    const data = values.map((value, i) => ({ label: i === 0 ? LONG_60 : `Retailer ${i + 1}`, value }));
    renderWithProviders(<ShareChart data={data} unit="usd" variant="donut" summary="Support by customer" />);
    const legend = screen.getByTestId('share-chart-legend');
    expect(within(legend).getByText(LONG_60)).toBeInTheDocument();
    expect(within(legend).getAllByRole('listitem')).toHaveLength(5);
    // 300 of the full 1 000 (all 12 slices), not of the 790 shown.
    expect(legend.textContent).toContain('30.0%');
    expect(screen.getByText('Top 5 of 12 shown · shares are of the full total')).toBeInTheDocument();
    // The data table lists every slice.
    expect(tableRows()).toHaveLength(12);
    expect(document.body.textContent).not.toMatch(/Other \(/);
  });
});

describe('number integrity: formatting changes, numbers do not', () => {
  const inputs: Array<{ name: string; v: number | null }> = [
    { name: 'Highveld Distribution', v: 18_400_000 },
    { name: 'Coastal Tech Supply', v: 1_234_567.89 },
    { name: 'Kwazulu Channel Partners', v: 4_200 },
    { name: 'Karoo', v: 99.5 },
    { name: 'Overberg', v: -1_500 },
    { name: 'Namakwa', v: 0.25 },
    { name: 'Nobody', v: null },
  ];
  const byName = new Map(inputs.map((d) => [d.name, d.v]));
  const units: MeasureUnit[] = ['zar', 'usd', 'units', 'count', 'percent', 'weeks', 'days', 'quarters', 'number'];

  it('CategoryBars', () => {
    for (const unit of units) {
      const { unmount } = renderWithProviders(
        <CategoryBars data={inputs.map((d) => ({ name: d.name, v: d.v }))} x="name" y="v" unit={unit} controls={false} xAxisTitle="Distributor" yAxisTitle="Value" />,
      );
      const rows = tableRows();
      expect(rows).toHaveLength(inputs.length);
      for (const [name, text] of rows) expect(text).toBe(formatChartValue(byName.get(name), unit, 'full'));
      unmount();
    }
  });

  it('PairedBars', () => {
    for (const unit of units) {
      const data = inputs.map((d, i) => ({ name: d.name, a: d.v, b: d.v == null ? null : d.v * (i + 1) }));
      const { unmount } = renderWithProviders(
        <PairedBars data={data} x="name" a="a" b="b" aLabel="Plan" bLabel="Shipped" unit={unit} controls={false} xAxisTitle="Customer" yAxisTitle="Value" />,
      );
      for (const [name, a, b] of tableRows()) {
        const row = data.find((d) => d.name === name)!;
        expect(a).toBe(formatChartValue(row.a, unit, 'full'));
        expect(b).toBe(formatChartValue(row.b, unit, 'full'));
      }
      unmount();
    }
  });

  it('TrendChart', () => {
    for (const unit of units) {
      const data = inputs.map((d, i) => ({ week: `W${i + 1}`, s: d.v, t: d.v == null ? null : -d.v / 3 }));
      const { unmount } = renderWithProviders(
        <TrendChart
          data={data}
          x="week"
          unit={unit}
          xAxisTitle="Week"
          yAxisTitle="Value"
          series={[
            { key: 's', label: 'Sell-out', kind: 'bar' },
            { key: 't', label: 'Trend', kind: 'line' },
          ]}
        />,
      );
      const rows = tableRows();
      expect(rows).toHaveLength(data.length);
      rows.forEach(([week, s, t], i) => {
        expect(week).toBe(data[i].week);
        expect(s).toBe(formatChartValue(data[i].s, unit, 'full'));
        expect(t).toBe(formatChartValue(data[i].t, unit, 'full'));
      });
      unmount();
    }
  });

  it('RankedBars', () => {
    for (const unit of units) {
      const { unmount } = renderWithProviders(
        <RankedBars data={inputs.map((d) => ({ label: d.name, value: d.v }))} unit={unit} max="all" summary="Value by distributor" xAxisTitle="Distributor" yAxisTitle="Value" />,
      );
      const rows = tableRows();
      expect(rows).toHaveLength(inputs.filter((d) => d.v != null).length);
      for (const [name, text] of rows) expect(text).toBe(formatChartValue(byName.get(name), unit, 'full'));
      unmount();
    }
  });

  it('ShareChart', () => {
    const data = inputs.filter((d) => d.v != null && d.v > 0).map((d) => ({ label: d.name, value: d.v as number }));
    const total = data.reduce((s, d) => s + d.value, 0);
    for (const unit of units) {
      const { unmount } = renderWithProviders(<ShareChart data={data} unit={unit} summary="Share by distributor" />);
      for (const [name, value, share] of tableRows()) {
        const v = data.find((d) => d.label === name)!.value;
        expect(value).toBe(formatChartValue(v, unit, 'full'));
        expect(share).toBe(`${formatNumber((v / total) * 100, { digits: 1, minDigits: 1 })}%`);
      }
      unmount();
    }
  });
});
