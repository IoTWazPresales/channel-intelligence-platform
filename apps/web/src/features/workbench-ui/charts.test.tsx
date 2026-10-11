import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import {
  ChartFigure,
  RankedBars,
  Sparkline,
  StateKey,
  TrendChart,
  formatMeasure,
  formatNumber,
  niceAxis,
  rankBars,
  sparklinePoints,
  thresholdState,
  unitWord,
} from './charts';

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
    expect(formatMeasure(1200, 'usd', 'short')).toBe('$1 200');
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
