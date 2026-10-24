import type { DashboardFilters, DefinitionV2 } from './builder/types';

export type WidgetVisual =
  | 'kpi'
  | 'table'
  | 'bar'
  | 'hbar'
  | 'stacked_bar'
  | 'line'
  | 'area'
  | 'pie'
  | 'donut'
  // N-0116 (0048): combo is MUST; dual_axis, scatter and pivot are accepted by the API (SHOULD, not drawn yet).
  | 'combo'
  | 'dual_axis'
  | 'scatter'
  | 'pivot';
export type PeriodGrain = 'week' | 'month' | 'quarter';

export type DashboardWidget = {
  id: number;
  dashboard_id: number;
  title: string;
  visual: WidgetVisual;
  metric_key: string;
  grains: string[];
  filters: Record<string, unknown>;
  period_grain: PeriodGrain | null;
  layout_json: { x?: number; y?: number; w?: number; h?: number } | null;
  saved_report_id: number | null;
  sort_order: number;
  /** N-0116: set = run v2 execute; null or absent (an API before 0048) = the v1 path as before. */
  definition_v2?: DefinitionV2 | null;
};

export type Dashboard = {
  id: number;
  name: string;
  description: string | null;
  visibility: string;
  shared_roles: string[];
  widgets: DashboardWidget[];
  /** N-0116: saved filter bar; `{}` by default, absent on an API before 0048. */
  filters_json?: Partial<DashboardFilters> | Record<string, never>;
  template_key?: string | null;
  owner_user_id?: number | null;
};

export type SemanticMetric = {
  id: string;
  key: string;
  label: string;
  status: string;
  formula: string;
  allowed_grains: string[][];
  refuse_all?: boolean;
  /** False when no query handler serves this metric yet: builders leave it out. */
  handler_backed?: boolean;
  calendar_period?: boolean;
  /** Catalog area (e.g. channel-ops); the metric list groups by it. */
  owner_surface?: string | null;
  notes?: string | null;
};

export type CatalogResponse = {
  version: number;
  source_doc: string;
  metrics: SemanticMetric[];
  dimensions: { id: string; label: string }[];
};

export type SeriesPoint = {
  bucket_key: string;
  bucket_start?: string;
  bucket_end?: string;
  value: number;
};

export type QueryResult = {
  ok: boolean;
  status: string;
  metric_key: string | null;
  grains: string[];
  period_grain?: string | null;
  validation: { ok: boolean; message: string; allowed_grains?: string[][] };
  invariants_applied: string[];
  data_vintage: Record<string, unknown> | null;
  value: unknown;
  rows: Record<string, unknown>[] | null;
  series: SeriesPoint[] | null;
  message: string | null;
  handler: string | null;
};

export const VOLUME_METRIC_KEYS = ['sellout_units', 'cst_sellthrough_units'] as const;

export function grainSetKey(grains: string[]): string {
  return [...grains]
    .map((g) => g.trim().toLowerCase())
    .filter(Boolean)
    .sort()
    .join('|');
}

export function labelGrainSet(grains: string[]): string {
  return grains.length ? grains.join(' × ') : 'no grain';
}
