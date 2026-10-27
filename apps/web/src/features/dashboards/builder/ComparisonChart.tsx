'use client';

import { Typography } from '@mui/material';
import { TrendChart, formatChartValue, type ChartClickEvent } from '@/features/workbench-ui/charts';
import { categoryPresentation } from '@/features/workbench-ui/ChartControls';
import { breakdownLabel, measureUnit } from './catalog';
import { measureHeading } from './advancedShape';
import { previousField } from './comparison';
import { breakdownColumns, catOf, type Cat } from './shape';
import type { CatalogV2, DefinitionV2, V2Measure, V2Response, V2Row } from './types';

/** Raw current/prior values share positions, never a stack or an invented aggregate. */
export function ComparisonChart({ response, def, measures, catalog, visual, label, height, onSelect, selectedKeys }: {
  response: V2Response; def: DefinitionV2; measures: V2Measure[]; catalog: CatalogV2;
  visual: 'bar' | 'line' | 'area'; label: string; height: number;
  onSelect?: (cat: Cat, e: ChartClickEvent) => void; selectedKeys?: string[];
}) {
  const period = def.query.breakdowns?.includes('period');
  const cols = breakdownColumns(response).filter((c) => c.id !== 'period' && def.query.breakdowns?.includes(c.id));
  const category = (row: V2Row) => {
    const parts = cols.map((c) => catOf(row, c));
    return { key: parts.map((p) => p.key).join('|') || 'all', label: parts.map((p) => p.label).join(' · '), cat: parts[0] ?? null };
  };
  const all = [...new Map(response.rows.map((r) => { const c = category(r); return [c.key, c]; })).values()];
  const categories = period && cols.length ? all.slice(0, 7) : all;
  const series = categories.flatMap((cat, ci) => measures.flatMap((m, mi) => [false, true].map((prior) => ({
    key: `${prior ? 'p' : 'c'}${ci}m${mi}`, label: `${cat.label ? `${cat.label} · ` : ''}${m.label}${prior ? `, ${label}` : ''}`,
    kind: visual === 'bar' ? 'bar' as const : visual === 'area' ? 'area' as const : 'line' as const,
    unit: measureUnit(m), ...(prior ? { tone: 'muted' as const, dash: '5 4' } : {}),
    cat: cat.cat, clickable: Boolean(cat.cat?.value != null && onSelect),
  }))));
  const points = new Map<string, V2Row>();
  for (const row of response.rows) {
    const cat = category(row), ci = categories.findIndex((c) => c.key === cat.key);
    if (ci < 0) continue;
    const x = period ? String(row.bucket_start) : cat.key;
    const point = points.get(x) ?? { x, __label: period ? String(row.bucket_key) : cat.label,
      __cat: period ? { key: `period:${row.bucket_key}`, breakdown: 'period', value: String(row.bucket_key), label: String(row.bucket_key), window: { from: String(row.bucket_start), to: String(row.bucket_end) } } : cat.cat,
      ...Object.fromEntries(series.map((s) => [s.key, null])) };
    measures.forEach((m, mi) => { point[`c${ci}m${mi}`] = row[m.id]; point[`p${ci}m${mi}`] = row[previousField(mi)]; });
    if (row.__previous_period) point.__previous_period = row.__previous_period;
    points.set(x, point);
  }
  const data = [...points.values()];
  if (period) data.sort((a, b) => String(a.x).localeCompare(String(b.x)));
  const xTitle = period ? `Period (${def.query.period?.grain ?? 'quarter'}), bucket start` : cols.map((c) => breakdownLabel(catalog, c.id)).join(' · ');
  const presentation = period ? undefined : categoryPresentation(def.query.sort, def.display?.top_n, measures.map((m) => m.id), cols.map((c) => c.id), 10);
  return <>
    <TrendChart data={data} x="x" series={series} height={height} unit={measureUnit(measures[0])}
      xTickFormat={(tick) => String(points.get(String(tick))?.__label ?? tick)} xAxisTitle={xTitle} yAxisTitle={measures.map(measureHeading).join(' / ')}
      categoryAxis={!period}
      initialControls={presentation}
      datumActions={onSelect ? (period ? 'period' : 'category') : undefined}
      summary={period ? undefined : 'Current and previous figures; missing values are not zero'}
      onPointClick={onSelect ? (row, _i, e) => { if (row.__cat) onSelect(row.__cat as Cat, e); } : undefined}
      onSeriesClick={onSelect ? (key, e) => { const cat = series.find((s) => s.key === key)?.cat; if (cat) onSelect(cat, e); } : undefined}
      selectedSeries={series.filter((s) => s.cat && selectedKeys?.includes(s.cat.key)).map((s) => s.key)}
      table={period ? { caption: 'Current and previous figures; missing values are not zero', columns: [xTitle, 'Previous bucket', ...series.map((s) => s.label)],
        rows: data.map((r) => [String(r.__label), String(r.__previous_period ?? '—'), ...series.map((s) => formatChartValue(typeof r[s.key] === 'number' ? r[s.key] as number : null, s.unit))]) } : undefined} />
    {all.length > categories.length ? <Typography variant="caption">{categories.length} categories shown; {all.length - categories.length} not shown. Narrow the filters to see the others.</Typography> : null}
  </>;
}
