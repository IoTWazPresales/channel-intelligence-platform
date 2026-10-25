/**
 * N-0116 builder types: the v2 catalog (`GET /semantics/v2/catalog`), the v2 query
 * (`POST /query/v2/execute`), the stored widget definition (`definition_v2`), the saved dashboard
 * filters (`filters_json`) and the starter templates (`GET /dashboards/templates`).
 *
 * Shapes follow the API half's contract (`.eif/audit/PROGRAMME_20261023/N0116_IMPL_API_REPORT.md` s.4)
 * and the N-0115 v2 query (`N0115_IMPL_REPORT.md` s.2). Every field the old API may not send is optional.
 */

export type V2Unit = 'units' | 'count' | 'usd' | 'zar' | 'ratio' | 'units_per_week' | 'usd_per_unit' | string;

export type V2Breakdown = {
  id: string;
  label: string;
  group: string;
  kind: 'period' | 'entity' | 'attribute' | 'local' | string;
  grains?: string[];
  /** Attribute / reference: the dimension it belongs to. */
  of?: string;
  /** Local breakdowns: the models that have it. */
  models?: string[];
};

export type V2Model = {
  id: string;
  label: string;
  customer_role?: string | null;
  breakdowns: string[];
  /** N-0116 S5: why a filter on any other breakdown is refused (the planner's own text). */
  filter_refusals?: Record<string, string>;
};

export type GovernedHonours = {
  handler: string | null;
  filters: string[];
  dates: boolean;
  all_time_only: boolean;
  one_value_per_filter?: boolean;
};

export type V2Measure = {
  id: string;
  label: string;
  unit: V2Unit | null;
  model: string | null;
  kind: 'base' | 'calculated' | 'governed';
  calc?: string;
  inputs?: string[];
  additivity: 'additive' | 'non_additive' | 'semi_additive' | null;
  breakdowns: string[];
  period_grains: string[];
  requires: string[];
  legacy_key: string | null;
  // Governed (v1 metric) only.
  grain_sets?: string[][];
  metric_id?: string;
  status?: string;
  handler_backed?: boolean;
  refuse_all?: boolean;
  refuse_reason?: string | null;
  hidden?: boolean;
  /** N-0116 S5. Absent on an API that predates 0048: treated as "honours nothing". */
  honours?: GovernedHonours;
};

export type V2Wall = { id: string; reason: string; keeps: { metric: string; grains: string[]; text: string }[] };

export type V2Pending = { id: string; reason: string };

export type CatalogV2 = {
  version: string;
  model_version?: number;
  source_doc?: string;
  groups: string[];
  breakdowns: V2Breakdown[];
  models: V2Model[];
  measures: V2Measure[];
  walls: V2Wall[];
  combination_rule?: string;
  limits: { max_breakdowns: number; default_limit: number; max_limit: number };
  pending: V2Pending[];
};

export type V2FilterValue = string | number;

export type V2Request = {
  measures: string[];
  breakdowns?: string[];
  filters?: Record<string, V2FilterValue | V2FilterValue[]>;
  period?: { grain?: string | null; from?: string | null; to?: string | null };
  sort?: { by: string; dir: 'asc' | 'desc' };
  limit?: number;
};

export type V2Column = {
  id: string;
  kind: 'breakdown' | 'measure';
  label: string;
  fields: string[];
  unit?: V2Unit | null;
  group?: string | null;
};

export type V2Refusal = { measure: string | null; reason: string; wall?: string | null };

export type V2Row = Record<string, unknown>;

export type V2Response = {
  ok: boolean;
  columns: V2Column[];
  rows: V2Row[];
  totals: Record<string, number | null | unknown>;
  truncated: boolean;
  refusals: V2Refusal[];
  explain?: {
    row_count?: number;
    data_vintage?: { min?: string | null; max?: string | null } | Record<string, unknown> | null;
    [k: string]: unknown;
  } | null;
  cache?: unknown;
};

/** Display options stored beside the query; every key is optional. */
export type WidgetDisplay = {
  /** S16 comparison series/columns, using the dashboard comparison mode. */
  compare?: boolean;
  top_n?: number;
  series?: Record<string, { kind?: 'bar' | 'line' | 'area'; axis?: 'left' | 'right' }>;
  kpi?: { compare?: boolean; sparkline?: boolean };
  table?: { rules?: ColourRule[] };
  /** Starter KPI caption, e.g. "as of latest report on or before {to}". */
  caption?: string;
};

export type ColourRuleOp = '<' | '<=' | '>' | '>=' | 'between';
export type ColourTone = 'good' | 'warn' | 'bad';
export type ColourRule = { measure: string; op: ColourRuleOp; value: number; value2?: number; tone: ColourTone };

export type DefinitionV2 = {
  v: 1;
  kind?: 'model' | 'governed';
  query: {
    measures: string[];
    breakdowns?: string[];
    period?: { grain?: string | null };
    filters?: Record<string, V2FilterValue[] | V2FilterValue>;
    sort?: { by: string; dir: 'asc' | 'desc' };
    limit?: number;
  };
  display?: WidgetDisplay;
  /** Explicit per-widget exceptions to the dashboard bar/chips. Own query filters still apply. */
  dashboard?: { ignore_filters?: string[]; fixed_window?: { from: string; to: string } };
  v1_equivalent?: boolean;
  migrated_from?: Record<string, unknown>;
};

export type DatePreset = 'last_13_weeks' | 'last_26_weeks' | 'last_52_weeks' | 'this_year' | 'last_quarter' | 'all_time' | 'custom';
export type CompareMode = 'none' | 'previous_period' | 'previous_year';

/** The filter keys the bar shows, in order (spec s.3). */
export const BAR_FILTER_KEYS = ['customer', 'distributor', 'product', 'bu', 'channel', 'region'] as const;
export type BarFilterKey = (typeof BAR_FILTER_KEYS)[number];

/** `dashboard.filters_json` (spec s.2.3). Other keys are v2 breakdown ids with a list value. */
export type DashboardFilters = {
  date: { preset: DatePreset; from: string | null; to: string | null };
  compare: CompareMode;
  required?: string[];
  [key: string]: unknown;
};

export type TemplateLeftOut = { what: string; reason: string; pending_id: string | null };

export type DashboardTemplate = {
  key: string;
  title: string;
  description: string;
  widget_count: number;
  required_filters: string[];
  filters_json?: DashboardFilters;
  left_out: TemplateLeftOut[];
};

export type TemplatesResponse = { count: number; items: DashboardTemplate[] };

/** A window of dates (inclusive ISO days); null = all time. */
export type DateWindow = { from: string; to: string } | null;
