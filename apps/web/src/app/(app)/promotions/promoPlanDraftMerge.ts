export type DirtyField =
  | 'estimate_qty'
  | 'cost_basis'
  | 'srp'
  | 'cover_weeks'
  | 'distributor_id'
  | 'pod_quarter';

export const DIRTY_FIELDS: DirtyField[] = [
  'estimate_qty',
  'cost_basis',
  'srp',
  'cover_weeks',
  'distributor_id',
  'pod_quarter',
];

export type IntakeWeighted = {
  cost_basis?: number | null;
  cost_source?: string | null;
  flags?: string[];
  bucket_a_on_hand?: Record<string, unknown> | null;
  bucket_b_intake?: Record<string, unknown> | null;
  planned_supply?: Record<string, unknown> | null;
  sellout_value?: Record<string, unknown> | null;
  disti_cost?: Record<string, unknown> | null;
  blend?: Record<string, unknown> | null;
  evidence?: Record<string, unknown> | null;
  not_in_blend?: string[];
};

export type SuggestionLine = {
  row_key: string;
  seed_line_id?: number | null;
  product_id: number;
  product_sku?: string | null;
  product_name?: string | null;
  distributor_id?: number | null;
  customer_id?: number | null;
  pod_quarter?: string | null;
  srp?: number | null;
  suggested_estimate_qty?: number;
  suggested_cost_basis?: number | null;
  suggested_cost_source?: string | null;
  cover?: { weeks?: number | null; source?: string; override_weeks?: number | null };
  intake_weighted?: IntakeWeighted;
  flags?: string[];
};

export type PlannerRow = {
  row_key: string;
  seed_line_id: number | null;
  product_id: number;
  product_sku: string | null;
  product_name: string | null;
  distributor_id: number | null;
  customer_id: number | null;
  pod_quarter: string | null;
  srp: number | null;
  estimate_qty: number;
  cost_basis: number | null;
  cover_weeks: number | null;
  cover_source: string;
  cover_override: number | null;
  suggested_srp: number | null;
  suggested_estimate_qty: number;
  suggested_cost_basis: number | null;
  suggested_distributor_id: number | null;
  suggested_pod_quarter: string | null;
  suggested_cover_weeks: number | null;
  dirty_fields: DirtyField[];
  intake_weighted: IntakeWeighted;
  flags: string[];
};

function identityKey(row: { row_key?: string; product_id: number; distributor_id?: number | null; pod_quarter?: string | null; seed_line_id?: number | null }): string {
  if (row.row_key) return row.row_key;
  return `${row.product_id}:${row.distributor_id ?? ''}:${row.pod_quarter ?? ''}:${row.seed_line_id ?? 'new'}`;
}

export function hydratePlannerRows(lines: SuggestionLine[]): PlannerRow[] {
  return lines.map((line) => {
    const coverWeeks = line.cover?.override_weeks ?? line.cover?.weeks ?? null;
    const qty = Number(line.suggested_estimate_qty ?? 0);
    return {
      row_key: identityKey(line),
      seed_line_id: line.seed_line_id ?? null,
      product_id: line.product_id,
      product_sku: line.product_sku ?? null,
      product_name: line.product_name ?? null,
      distributor_id: line.distributor_id ?? null,
      customer_id: line.customer_id ?? null,
      pod_quarter: line.pod_quarter ?? null,
      srp: line.srp ?? null,
      estimate_qty: qty,
      cost_basis: line.suggested_cost_basis ?? line.intake_weighted?.cost_basis ?? null,
      cover_weeks: coverWeeks,
      cover_source: line.cover?.source ?? 'tenant_default',
      cover_override: line.cover?.override_weeks ?? null,
      suggested_srp: line.srp ?? null,
      suggested_estimate_qty: qty,
      suggested_cost_basis: line.suggested_cost_basis ?? line.intake_weighted?.cost_basis ?? null,
      suggested_distributor_id: line.distributor_id ?? null,
      suggested_pod_quarter: line.pod_quarter ?? null,
      suggested_cover_weeks: line.cover?.weeks ?? null,
      dirty_fields: [],
      intake_weighted: line.intake_weighted ?? {},
      flags: line.flags ?? line.intake_weighted?.flags ?? [],
    };
  });
}

function isDirty(row: PlannerRow, field: DirtyField): boolean {
  return row.dirty_fields.includes(field);
}

export function mergePromoPlanSuggestions(current: PlannerRow[], incoming: SuggestionLine[]): PlannerRow[] {
  const hydrated = hydratePlannerRows(incoming);
  const byKey = new Map(current.map((row) => [row.row_key, row]));
  return hydrated.map((fresh) => {
    const prev = byKey.get(fresh.row_key);
    if (!prev) return fresh;
    const dirty = [...prev.dirty_fields];
    const next: PlannerRow = {
      ...fresh,
      dirty_fields: dirty,
      estimate_qty: isDirty(prev, 'estimate_qty') ? prev.estimate_qty : fresh.suggested_estimate_qty,
      cost_basis: isDirty(prev, 'cost_basis') ? prev.cost_basis : fresh.suggested_cost_basis,
      srp: isDirty(prev, 'srp') ? prev.srp : fresh.suggested_srp,
      cover_weeks: isDirty(prev, 'cover_weeks') ? prev.cover_weeks : fresh.cover_weeks,
      cover_override: isDirty(prev, 'cover_weeks') ? prev.cover_override : fresh.cover_override,
      distributor_id: isDirty(prev, 'distributor_id') ? prev.distributor_id : fresh.suggested_distributor_id,
      pod_quarter: isDirty(prev, 'pod_quarter') ? prev.pod_quarter : fresh.suggested_pod_quarter,
    };
    return next;
  });
}

export function markDirty(row: PlannerRow, field: DirtyField, value: unknown): PlannerRow {
  const dirty = row.dirty_fields.includes(field) ? row.dirty_fields : [...row.dirty_fields, field];
  const next: PlannerRow = { ...row, dirty_fields: dirty };
  if (field === 'estimate_qty') next.estimate_qty = Number(value ?? 0);
  if (field === 'cost_basis') next.cost_basis = value == null || value === '' ? null : Number(value);
  if (field === 'srp') next.srp = value == null || value === '' ? null : Number(value);
  if (field === 'cover_weeks') {
    const weeks = value == null || value === '' ? null : Number(value);
    next.cover_weeks = weeks;
    next.cover_override = weeks;
    next.cover_source = weeks == null ? row.cover_source : 'override';
  }
  if (field === 'distributor_id') next.distributor_id = value == null || value === '' ? null : Number(value);
  if (field === 'pod_quarter') next.pod_quarter = value == null || value === '' ? null : String(value);
  return next;
}

export function resetField(row: PlannerRow, field: DirtyField): PlannerRow {
  const dirty = row.dirty_fields.filter((f) => f !== field);
  const next: PlannerRow = { ...row, dirty_fields: dirty };
  if (field === 'estimate_qty') next.estimate_qty = row.suggested_estimate_qty;
  if (field === 'cost_basis') next.cost_basis = row.suggested_cost_basis;
  if (field === 'srp') next.srp = row.suggested_srp;
  if (field === 'cover_weeks') {
    next.cover_weeks = row.suggested_cover_weeks;
    next.cover_override = null;
    next.cover_source = row.cover_source === 'override' ? 'tenant_default' : row.cover_source;
  }
  if (field === 'distributor_id') next.distributor_id = row.suggested_distributor_id;
  if (field === 'pod_quarter') next.pod_quarter = row.suggested_pod_quarter;
  return next;
}

export function toCreateLines(rows: PlannerRow[]): Array<Record<string, unknown>> {
  return rows.map((row) => ({
    product_id: row.product_id,
    distributor_id: row.distributor_id,
    srp: row.srp,
    estimate_qty: row.estimate_qty,
    cost_basis: row.cost_basis,
    pod_quarter: row.pod_quarter,
    cover_override: row.cover_override,
    dirty_fields: row.dirty_fields,
    seed_line_id: row.seed_line_id,
  }));
}

export function toRecomputeSpecs(rows: PlannerRow[]): Array<Record<string, unknown>> {
  return rows.map((row) => ({
    product_id: row.product_id,
    distributor_id: row.distributor_id,
    pod_quarter: row.pod_quarter,
    srp: row.srp,
    estimate_qty: row.estimate_qty,
    cover_override: row.cover_override,
    seed_line_id: row.seed_line_id,
  }));
}
