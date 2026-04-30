'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  InputLabel,
  Link as MuiLink,
  MenuItem,
  Paper,
  Select,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, GridOptions, ICellRendererParams } from 'ag-grid-community';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { AddProductSetDialog } from '@/features/commercial-planner/AddProductSetDialog';
import { ColumnSelectorModal, type ColumnMetadata } from '@/features/commercial-planner/ColumnSelectorModal';
import { CommercialDataMap } from '@/features/commercial-planner/CommercialDataMap';
import { CurrentLineupSection } from '@/features/commercial-planner/CurrentLineupSection';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { LineEconomicsWaterfall } from '@/features/commercial-planner/LineEconomicsWaterfall';
import { PlannerDefaultsMaintenance } from '@/features/commercial-planner/PlannerDefaultsMaintenance';
import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type Plan = {
  id: number;
  plan_name: string;
  status: string;
  period_start: string;
  period_end: string | null;
  owner: string | null;
  country_code: string | null;
  currency_code: string;
  line_count: number;
  notes: string | null;
};

type PlanLine = {
  id: number;
  customer_id: number;
  distributor_id: number;
  product_id: number;
  customer_code?: string | null;
  customer_name?: string | null;
  distributor_code?: string | null;
  distributor_name?: string | null;
  product_sku?: string | null;
  product_name?: string | null;
  product_part_number?: string | null;
  product_model_name?: string | null;
  product_sales_model_name?: string | null;
  product_category?: string | null;
  product_form_factor?: string | null;
  product_lifecycle_status?: string | null;
  product_line?: string | null;
  product_series_name?: string | null;
  product_business_unit?: string | null;
  product_spec_cpu?: string | null;
  product_spec_processor?: string | null;
  product_spec_ram?: string | null;
  product_spec_storage?: string | null;
  product_spec_gpu?: string | null;
  product_spec_display?: string | null;
  product_spec_warranty?: string | null;
  product_spec_os?: string | null;
  product_spec_colour?: string | null;
  /** Flattened specs_json string map for optional dynamic columns. */
  product_specs_flat?: Record<string, string>;
  effective_customer_margin_pct?: number | null;
  effective_customer_rebate_pct?: number | null;
  effective_distributor_margin_pct?: number | null;
  effective_vat_rate_pct?: number | null;
  effective_fx_rate_to_usd?: number | null;
  effective_reserve_total_pct?: number | null;
  effective_promo_reserve_split_pct?: number | null;
  effective_controlled_cost_usd_per_unit?: number | null;
  calc_sell_in_price_local?: number | null;
  calc_distributor_net_local?: number | null;
  target_units: number;
  target_srp_local: number;
  promo_srp_local: number | null;
  promo_mix_pct: number;
  calc_sell_in_price_usd: number | null;
  calc_buy_price_usd: number | null;
  calc_promo_reserve_usd: number | null;
  calc_non_promo_reserve_usd: number | null;
  calc_internal_gp_usd: number | null;
  calc_customer_gp_pct: number | null;
  calc_distributor_gp_pct: number | null;
  calc_flags: string[];
  calc_explanation: string | null;
  override_landed_cost_usd: number | null;
  economics_line_trust?: 'ok' | 'warning' | 'blocked' | string;
  economics_line_trust_reasons?: string[];
  economics_field_provenance?: Record<string, { source: string; trusted?: boolean; detail?: string }>;
};

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };
type ProductPick = {
  id: number;
  sku: string;
  name: string;
  part_number: string | null;
  sales_model_name: string | null;
  model_name: string | null;
  category: string | null;
  form_factor?: string | null;
  product_line: string | null;
  series_name: string | null;
  lifecycle_status: string | null;
  business_unit?: string | null;
  specs_preview?: Record<string, string> | null;
};

type CustomerListResponse = { items: CustomerPick[] };
type DistributorListResponse = { items: DistributorPick[] };
type ProductListResponse = { items: ProductPick[] };

type Suggestion = {
  type: string;
  value: number | { target_srp_local: number; promo_srp_local: number };
  reason: string;
  confidence: string;
  factors: Record<string, unknown>;
};

type SuggestionBundle = {
  line_id: number;
  suggestions: Suggestion[];
  _meta?: {
    lineup_job_id: number | null;
    lineup_period_label: string | null;
    data_sources: {
      sellout: boolean;
      prior_planned: boolean;
      forecast: boolean;
      net_price: boolean;
      lineup: boolean;
    };
  };
};

type Summary = {
  line_count: number;
  total_units: number;
  total_internal_gp_usd: number;
  total_promo_reserve_usd: number;
  total_non_promo_reserve_usd: number;
  flags: string[];
};

type RecalcFeedback = {
  updated: number;
  economics_trust: string;
  economics_trust_note: string | null;
  economics_plan_trust?: string;
  recalculate_trust_summary?: {
    lines_trusted_ok: number;
    lines_warning: number;
    lines_blocked: number;
    top_blocker_flags: string[];
  };
};

type LineupJob = {
  id: number;
  file_name: string;
  status: string;
  stage: string;
  period_label: string | null;
  country_code: string | null;
  currency_code: string | null;
  line_count: number;
};

type LineupCoverageLine = {
  id: number;
  source_row_number: number;
  product_id: number | null;
  product_sku: string | null;
  product_name: string | null;
  part_number_raw: string | null;
  model_raw: string | null;
  base_unit_raw: string | null;
  quantity_units: number | null;
  msrp_local: number | null;
  promo_price_local: number | null;
  month_split_json: Record<string, number> | null;
  dap_local: number | null;
  actual_dap_local: number | null;
  disti_cost_local: number | null;
  rebate_pct: number | null;
  dealer_margin_pct: number | null;
  vat_pct: number | null;
  disti_margin_pct: number | null;
  customer_token: string | null;
  header_customer_id: number | null;
  header_customer_code: string | null;
  header_customer_name: string | null;
  header_distributor_id: number | null;
  header_distributor_code: string | null;
  header_distributor_name: string | null;
  diagnostic_codes: string[];
  has_warnings: boolean;
  has_unknown_customer: boolean;
  period_label: string | null;
  country_code: string | null;
  currency_code: string | null;
};

type LineupEvidenceFields = {
  dap_local: number | null;
  actual_dap_local: number | null;
  disti_cost_local: number | null;
  vat_pct: number | null;
  disti_margin_pct: number | null;
  rebate_pct: number | null;
  dealer_margin_pct: number | null;
  total_quantity_units: number | null;
  msrp_local: number | null;
  promo_price_local: number | null;
  period_label: string | null;
};

type LineupProductGap = {
  product_id: number;
  product_sku: string;
  product_name: string;
  has_sku_assumption: boolean;
  lineup_evidence: LineupEvidenceFields;
  assumption_gaps: string[];
  cost_semantics_note: string;
};

type LineupEvidence = {
  product_id: number;
  lineup_job_id: number | null;
  evidence: {
    msrp_local: number | null;
    promo_price_local: number | null;
    dap_local: number | null;
    actual_dap_local: number | null;
    disti_margin_pct: number | null;
    vat_pct: number | null;
    rebate_pct: number | null;
    total_quantity_units: number | null;
    line_count: number;
    period_label: string | null;
  } | null;
  cost_semantics_note: string;
};

type PlanReadiness = {
  plan_id: number;
  line_count: number;
  missing_customer_term: number;
  missing_distributor_term: number;
  missing_sku_assumption: number;
  invalid_controlled_cost?: number;
  invalid_fx?: number;
  invalid_vat?: number;
  invalid_reserve?: number;
  using_unassigned_distributor?: number;
  lines_with_calc_flags: number;
  ready: boolean;
  readiness_summary: string;
};

/**
 * Format a stored margin/percentage value for display.
 * Convention: values < 1.0 are stored as decimal fractions (0.0724 = 7.24%);
 * values >= 1.0 are already percentage points (7.24 = 7.24%).
 * This threshold is safe for realistic disti/dealer margins in the 0–30% range.
 */
export function fmtMarginPct(v: number | null | undefined): string {
  if (v == null) return '—';
  const pct = v < 1.0 ? v * 100 : v;
  return `${pct.toFixed(2)}%`;
}

/** Format a local-currency price value with 2 decimal places. */
export function fmtCurrency(v: number | null | undefined): string {
  if (v == null) return '—';
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Economics pipeline persists USD-valued outputs today (see commercial_plan_line.calc_*_usd). */
export const ECONOMICS_PIPELINE_CURRENCY = 'USD';

export function fmtMoneyWithCcy(v: number | null | undefined, currencyCode: string): string {
  if (v == null) return '—';
  return `${fmtCurrency(v)} ${currencyCode}`;
}

/** Translate a calc_flag / readiness code to a user-facing message (full text, tooltips). */
export function fmtFlag(flag: string): string {
  const labels: Record<string, string> = {
    missing_sku_assumption:
      'Controlled cost missing — add SKU assumptions in Planner defaults (not populated from DAP)',
    missing_or_invalid_landed_cost: 'Controlled cost unavailable — verify SKU assumption or line override',
    missing_distributor_term:
      'Missing distributor terms — configure on the Distributor admin page or bulk edit in Planner defaults',
    missing_customer_term:
      'Missing customer terms — configure on the Customer admin page or bulk edit in Planner defaults',
    non_positive_target_units: 'Units must be positive',
    non_positive_target_srp: 'Customer-facing list price must be positive',
    invalid_fx_rate_to_usd: 'FX rate invalid',
    impossible_margin_stack: 'Margin stack unsustainable (margins ≥ 95%)',
    margin_floor_breach: 'Margin below floor — buy price is under controlled cost',
    reserve_breach: 'Reserve exceeds 80% of revenue',
    impossible_economics: 'Cannot compute sell-in price',
    partial_margin_stack: 'Partial margin stack — some terms defaulted to zero',
    economics_placeholder_fx_without_sku: 'FX used as placeholder without SKU economics — untrusted',
    economics_placeholder_vat_without_sku: 'VAT used as placeholder without SKU economics — untrusted',
    economics_placeholder_reserves_without_sku: 'Reserves used as placeholder without SKU economics — untrusted',
    unassigned_distributor_placeholder: 'UNASSIGNED distributor placeholder — assign a distributor for trusted channel economics',
  };
  return labels[flag] ?? flag;
}

/** Short label for Issues column chips (no raw snake_case in the cell). */
export function fmtIssueChipLabel(flag: string): string {
  const short: Record<string, string> = {
    missing_sku_assumption: 'Controlled cost missing',
    missing_or_invalid_landed_cost: 'Controlled cost unavailable',
    missing_distributor_term: 'Missing distributor terms',
    missing_customer_term: 'Missing customer terms',
    non_positive_target_units: 'Invalid units',
    non_positive_target_srp: 'Invalid list price',
    invalid_fx_rate_to_usd: 'Invalid FX',
    impossible_margin_stack: 'Unsustainable margin stack',
    margin_floor_breach: 'Margin below floor',
    reserve_breach: 'Reserve breach',
    impossible_economics: 'Cannot compute sell-in',
    partial_margin_stack: 'Partial margin stack',
    economics_placeholder_fx_without_sku: 'FX placeholder without SKU economics',
    economics_placeholder_vat_without_sku: 'VAT placeholder without SKU economics',
    economics_placeholder_reserves_without_sku: 'Reserve placeholder without SKU economics',
    unassigned_distributor_placeholder: 'UNASSIGNED distributor — review before trusting',
  };
  return short[flag] ?? (flag.includes('_') ? flag.replace(/_/g, ' ') : flag);
}

const BLOCKING_ECONOMICS_FLAGS = new Set([
  'missing_sku_assumption',
  'missing_or_invalid_landed_cost',
  'invalid_fx_rate_to_usd',
  'impossible_economics',
  'non_positive_target_units',
  'non_positive_target_srp',
]);

/** True when line calc_flags indicate GP/reserve outputs must not be trusted as complete economics. */
export function lineHasBlockingEconomicsFlags(line: { calc_flags?: string[] } | null | undefined): boolean {
  if (!line?.calc_flags?.length) return false;
  return line.calc_flags.some((f) => BLOCKING_ECONOMICS_FLAGS.has(f));
}

export function roundPlannerUnits(n: number): number {
  return Math.round(Number(n));
}

/** Sum month_split_json values for lineup-derived default units (read-only). */
export function monthSplitTotalUnits(m: Record<string, number> | null | undefined): number | null {
  if (!m || typeof m !== 'object') return null;
  let t = 0;
  for (const v of Object.values(m)) {
    const n = Number(v);
    if (Number.isFinite(n)) t += n;
  }
  return t > 0 ? t : null;
}

function coverageLineupProductLabel(row: LineupCoverageLine): string {
  return (
    row.product_name?.trim() ||
    row.model_raw?.trim() ||
    row.product_sku?.trim() ||
    row.part_number_raw?.trim() ||
    '—'
  );
}

function coverageLineupCustomerCell(row: LineupCoverageLine): string {
  if (row.header_customer_id != null) {
    const bits = [row.header_customer_code, row.header_customer_name].filter((x) => x?.trim());
    if (bits.length) return bits.join(' — ');
  }
  const t = row.customer_token?.trim();
  if (t) return `${t} (unresolved)`;
  return '—';
}

function coverageLineupDistributorCell(row: LineupCoverageLine): string {
  if (row.header_distributor_id != null) {
    const bits = [row.header_distributor_code, row.header_distributor_name].filter((x) => x?.trim());
    if (bits.length) return bits.join(' — ');
  }
  return '—';
}

/** Model / sales model for grid and detail (read-only from DimProduct). */
export function fmtModelSalesModel(line: {
  product_model_name?: string | null;
  product_sales_model_name?: string | null;
}): string {
  const m = line.product_model_name?.trim();
  const s = line.product_sales_model_name?.trim();
  if (m && s && m !== s) return `${m} / ${s}`;
  return m || s || '—';
}

/** Tooltip text when GP/reserve cells are blocked by readiness flags. */
export function economicsBlockingTooltip(line: PlanLine | undefined): string | undefined {
  if (!line || !lineHasBlockingEconomicsFlags(line)) return undefined;
  const msgs = (line.calc_flags ?? [])
    .filter((f) => BLOCKING_ECONOMICS_FLAGS.has(f))
    .map((f) => fmtFlag(f));
  return msgs.length ? msgs.join(' · ') : 'Economics blocked — see Issues column.';
}

const SPECS_OPTIONAL_FIELDS = [
  'product_spec_cpu',
  'product_spec_processor',
  'product_spec_warranty',
  'product_spec_os',
  'product_spec_colour',
] as const;

const CATALOGUE_OPTIONAL_FIELDS = [
  'product_category',
  'product_form_factor',
  'product_lifecycle_status',
  'product_line',
  'product_series_name',
  'product_business_unit',
] as const;

const COMMERCIAL_TERM_OPTIONAL_FIELDS = [
  'effective_customer_margin_pct',
  'effective_customer_rebate_pct',
  'effective_distributor_margin_pct',
  'effective_vat_rate_pct',
  'effective_fx_rate_to_usd',
  'effective_reserve_total_pct',
  'effective_promo_reserve_split_pct',
  'effective_controlled_cost_usd_per_unit',
] as const;

const PLANNING_OPTIONAL_FIELDS = ['promo_mix_pct'] as const;

const USD_OUTPUT_OPTIONAL_FIELDS = [
  'calc_sell_in_price_local',
  'calc_distributor_net_local',
  'calc_sell_in_price_usd',
  'calc_internal_gp_usd',
  'calc_buy_price_usd',
  'calc_promo_reserve_usd',
  'calc_non_promo_reserve_usd',
] as const;

const OPTIONAL_GRID_COL_FIELDS = [
  ...SPECS_OPTIONAL_FIELDS,
  ...CATALOGUE_OPTIONAL_FIELDS,
  ...COMMERCIAL_TERM_OPTIONAL_FIELDS,
  ...PLANNING_OPTIONAL_FIELDS,
  ...USD_OUTPUT_OPTIONAL_FIELDS,
] as const;

type OptionalGridColField = (typeof OPTIONAL_GRID_COL_FIELDS)[number];

const LS_GRID_COLS_V4 = 'cip.commercial-planner.gridColumns.v4';
const LS_SPEC_OPTIONAL_KEYS = 'cip.commercial-planner.optionalSpecKeys.v1';
const LS_GRID_COLS_V3 = 'cip.commercial-planner.gridColumns.v3';
const LS_GRID_COLS_V2 = 'cip.commercial-planner.gridColumns.v2';
const LS_OPTIONAL_COLS_V1 = 'cip.commercial-planner.optionalColumns.v1';

const OPTIONAL_COLUMN_LABELS: Record<OptionalGridColField, string> = {
  product_spec_cpu: 'CPU / chipset (spec)',
  product_spec_processor: 'Processor (spec)',
  product_spec_warranty: 'Warranty',
  product_spec_os: 'OS',
  product_spec_colour: 'Colour',
  product_category: 'Category',
  product_form_factor: 'Form factor',
  product_lifecycle_status: 'Lifecycle',
  product_line: 'Product line',
  product_series_name: 'Series',
  product_business_unit: 'Business unit',
  effective_customer_margin_pct: 'Customer margin % (effective)',
  effective_customer_rebate_pct: 'Customer rebate % (effective)',
  effective_distributor_margin_pct: 'Distributor margin % (effective)',
  effective_vat_rate_pct: 'VAT % (effective)',
  effective_fx_rate_to_usd: 'FX: plan currency per 1 USD (effective)',
  effective_reserve_total_pct: 'Reserve total % (effective)',
  effective_promo_reserve_split_pct: 'Promo reserve split % (effective)',
  effective_controlled_cost_usd_per_unit: `Controlled cost (${ECONOMICS_PIPELINE_CURRENCY} / unit, effective)`,
  promo_mix_pct: 'Promo mix %',
  calc_sell_in_price_local: 'Estimated OEM/channel sell-in (plan currency / unit)',
  calc_distributor_net_local: 'Estimated distributor net (plan currency / unit)',
  calc_sell_in_price_usd: `Estimated OEM/channel sell-in (${ECONOMICS_PIPELINE_CURRENCY} / unit)`,
  calc_internal_gp_usd: `Estimated internal GP (${ECONOMICS_PIPELINE_CURRENCY}, total, after reserves)`,
  calc_buy_price_usd: `Estimated distributor net (${ECONOMICS_PIPELINE_CURRENCY} / unit)`,
  calc_promo_reserve_usd: `Promo reserve (${ECONOMICS_PIPELINE_CURRENCY})`,
  calc_non_promo_reserve_usd: `Non-promo reserve (${ECONOMICS_PIPELINE_CURRENCY})`,
};

function defaultOptionalVisibility(): Record<OptionalGridColField, boolean> {
  return {
    product_spec_cpu: false,
    product_spec_processor: false,
    product_spec_warranty: false,
    product_spec_os: false,
    product_spec_colour: false,
    product_category: false,
    product_form_factor: false,
    product_lifecycle_status: false,
    product_line: false,
    product_series_name: false,
    product_business_unit: false,
    effective_customer_margin_pct: false,
    effective_customer_rebate_pct: false,
    effective_distributor_margin_pct: false,
    effective_vat_rate_pct: false,
    effective_fx_rate_to_usd: false,
    effective_reserve_total_pct: false,
    effective_promo_reserve_split_pct: false,
    effective_controlled_cost_usd_per_unit: false,
    promo_mix_pct: false,
    calc_sell_in_price_local: false,
    calc_distributor_net_local: false,
    calc_sell_in_price_usd: false,
    calc_internal_gp_usd: false,
    calc_buy_price_usd: false,
    calc_promo_reserve_usd: false,
    calc_non_promo_reserve_usd: false,
  };
}

type SuggestionPreviewState = {
  key: string;
  lineId: number;
  suggestionType: string;
  applyValue: unknown;
  rows: { label: string; from: string; to: string }[];
  roundNote?: string;
};

function buildSuggestionPreview(line: PlanLine, s: Suggestion, key: string): SuggestionPreviewState | null {
  if (s.type === 'target_units') {
    const raw = Number(s.value);
    const rounded = roundPlannerUnits(raw);
    const roundNote = raw !== rounded ? 'Rounded to whole unit (planner uses integer quantities).' : undefined;
    return {
      key,
      lineId: line.id,
      suggestionType: s.type,
      applyValue: rounded,
      rows: [{ label: 'Units', from: String(line.target_units), to: String(rounded) }],
      roundNote,
    };
  }
  if (s.type === 'pricing_band' && s.value != null && typeof s.value === 'object' && !Array.isArray(s.value)) {
    const v = s.value as { target_srp_local: number; promo_srp_local: number };
    return {
      key,
      lineId: line.id,
      suggestionType: s.type,
      applyValue: s.value,
      rows: [
        {
          label: 'Customer-facing list price',
          from: fmtCurrency(line.target_srp_local),
          to: fmtCurrency(v.target_srp_local),
        },
        {
          label: 'Campaign / event price',
          from: line.promo_srp_local != null ? fmtCurrency(line.promo_srp_local) : '—',
          to: fmtCurrency(v.promo_srp_local),
        },
      ],
    };
  }
  if (s.type === 'promo_mix_pct') {
    const newMix = Number(s.value);
    return {
      key,
      lineId: line.id,
      suggestionType: s.type,
      applyValue: newMix,
      rows: [
        {
          label: 'Promo mix',
          from: `${(line.promo_mix_pct * 100).toFixed(1)}%`,
          to: `${(newMix * 100).toFixed(1)}%`,
        },
      ],
    };
  }
  return {
    key,
    lineId: line.id,
    suggestionType: s.type,
    applyValue: s.value,
    rows: [{ label: 'Value', from: '—', to: typeof s.value === 'object' ? JSON.stringify(s.value) : String(s.value) }],
  };
}

/** Human-readable label for a suggestion type. */
export function sugTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    target_units: 'Suggested units',
    pricing_band: 'Pricing anchor',
    promo_mix_pct: 'Promo split',
  };
  return labels[type] ?? type;
}

async function fetchCustomers(q: string, signal: AbortSignal): Promise<CustomerPick[]> {
  const res = await apiGet<CustomerListResponse>(
    `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q)}`,
    { signal }
  );
  return res.items;
}

async function fetchDistributors(q: string, signal: AbortSignal): Promise<DistributorPick[]> {
  const res = await apiGet<DistributorListResponse>(
    `/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(q)}`,
    { signal }
  );
  return res.items;
}

async function fetchProducts(q: string, signal: AbortSignal): Promise<ProductPick[]> {
  const res = await apiGet<ProductListResponse>(
    `/api/v1/products?page=1&page_size=25&q=${encodeURIComponent(q)}`,
    { signal }
  );
  return res.items;
}

function formatProductSearchOptionLabel(o: ProductPick): string {
  const primary = [o.sku?.trim() || '—', o.sales_model_name || o.model_name || o.name || '']
    .filter((x) => String(x).trim())
    .join(' · ');
  const bits: string[] = [];
  if (o.part_number?.trim()) bits.push(`Part # ${o.part_number.trim()}`);
  if (o.category?.trim()) bits.push(o.category.trim());
  if (o.form_factor?.trim()) bits.push(o.form_factor.trim());
  if (o.product_line?.trim()) bits.push(`Product line: ${o.product_line.trim()}`);
  if (o.series_name?.trim()) bits.push(`Series: ${o.series_name.trim()}`);
  if (o.lifecycle_status?.trim()) bits.push(`Lifecycle: ${o.lifecycle_status.trim()}`);
  if (o.business_unit?.trim()) bits.push(`BU: ${o.business_unit.trim()}`);
  if (o.specs_preview && Object.keys(o.specs_preview).length) {
    const specLine = Object.entries(o.specs_preview)
      .filter(([, v]) => v)
      .slice(0, 4)
      .map(([k, v]) => `${k}: ${v}`)
      .join(' · ');
    if (specLine) bits.push(specLine);
  }
  return bits.length ? `${primary} — ${bits.join(' · ')}` : primary;
}

function lineEntitySummary(line: PlanLine | undefined): string {
  if (!line) return '';
  const c = [line.customer_code, line.customer_name].filter(Boolean).join(' — ');
  const d = [line.distributor_code, line.distributor_name].filter(Boolean).join(' — ');
  const p = [line.product_sku, line.product_name].filter(Boolean).join(' — ');
  return [c && `Cust: ${c}`, d && `Dist: ${d}`, p && `SKU: ${p}`].filter(Boolean).join(' · ');
}

export default function CommercialPlannerPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [addPlanOpen, setAddPlanOpen] = useState(false);
  const [addLineOpen, setAddLineOpen] = useState(false);
  const [editLineOpen, setEditLineOpen] = useState(false);
  const [editingLine, setEditingLine] = useState<PlanLine | null>(null);
  const [editCustomer, setEditCustomer] = useState<CustomerPick | null>(null);
  const [editDistributor, setEditDistributor] = useState<DistributorPick | null>(null);
  const [editProduct, setEditProduct] = useState<ProductPick | null>(null);
  const [dismissed, setDismissed] = useState<Record<string, boolean>>({});
  const [planDraft, setPlanDraft] = useState({
    plan_name: '',
    period_start: new Date().toISOString().slice(0, 10),
    owner: 'planner',
    currency_code: 'USD',
  });
  const [lineCustomer, setLineCustomer] = useState<CustomerPick | null>(null);
  const [lineDistributor, setLineDistributor] = useState<DistributorPick | null>(null);
  const [lineProduct, setLineProduct] = useState<ProductPick | null>(null);
  const [lineDraft, setLineDraft] = useState({
    target_units: '',
    target_srp_local: '',
    promo_srp_local: '',
    promo_mix_pct: '0.5',
  });

  const [lineupJobId, setLineupJobId] = useState<number | null>(null);
  const [coverageFilter, setCoverageFilter] = useState('');
  const [showProductGaps, setShowProductGaps] = useState(true);
  const [showGuide, setShowGuide] = useState(false);
  const [selectedLineId, setSelectedLineId] = useState<number | null>(null);
  const [recalcFeedback, setRecalcFeedback] = useState<RecalcFeedback | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [optionalColsHydrated, setOptionalColsHydrated] = useState(false);
  const [optionalVisible, setOptionalVisible] = useState<Record<OptionalGridColField, boolean>>(() =>
    defaultOptionalVisibility()
  );
  const [suggestionPreview, setSuggestionPreview] = useState<SuggestionPreviewState | null>(null);
  const [addProductSetOpen, setAddProductSetOpen] = useState(false);
  const [columnSelectorOpen, setColumnSelectorOpen] = useState(false);
  const [deletePlanOpen, setDeletePlanOpen] = useState(false);
  const [addFromLineupOpen, setAddFromLineupOpen] = useState(false);
  const [addLineupJobId, setAddLineupJobId] = useState<number | null>(null);
  const [lineupModalFilter, setLineupModalFilter] = useState('');
  const [lineupResolvedOnly, setLineupResolvedOnly] = useState(false);
  const [lineupUnresolvedCustOnly, setLineupUnresolvedCustOnly] = useState(false);
  const [lineupWarningsOnly, setLineupWarningsOnly] = useState(false);
  const [lineupSelectedIds, setLineupSelectedIds] = useState<number[]>([]);
  const [lineupFbCustomer, setLineupFbCustomer] = useState<CustomerPick | null>(null);
  const [lineupFbDistributor, setLineupFbDistributor] = useState<DistributorPick | null>(null);
  const [lineupBatchSummary, setLineupBatchSummary] = useState<string | null>(null);
  const [lineupBatchRunning, setLineupBatchRunning] = useState(false);
  const [stagedLineupSummary, setStagedLineupSummary] = useState<{ caseId: number | null; lineCount: number }>({
    caseId: null,
    lineCount: 0,
  });
  const [optionalSpecKeyVisible, setOptionalSpecKeyVisible] = useState<Record<string, boolean>>({});
  const [specKeyPrefsLoaded, setSpecKeyPrefsLoaded] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const rawV4 = localStorage.getItem(LS_GRID_COLS_V4);
      if (rawV4) {
        const parsed = JSON.parse(rawV4) as { visibleOptional?: Partial<Record<OptionalGridColField, boolean>> };
        if (parsed.visibleOptional && typeof parsed.visibleOptional === 'object') {
          setOptionalVisible((prev) => ({ ...prev, ...parsed.visibleOptional }));
        }
        setOptionalColsHydrated(true);
        return;
      }
      // Migrate from v3
      const rawV3 = localStorage.getItem(LS_GRID_COLS_V3);
      if (rawV3) {
        const parsed = JSON.parse(rawV3) as { optional?: Partial<Record<OptionalGridColField, boolean>> };
        if (parsed.optional && typeof parsed.optional === 'object') {
          setOptionalVisible((prev) => ({ ...prev, ...parsed.optional }));
        }
        setOptionalColsHydrated(true);
        return;
      }
      const rawV2 = localStorage.getItem(LS_GRID_COLS_V2);
      if (rawV2) {
        const parsed = JSON.parse(rawV2) as { optional?: Partial<Record<string, boolean>> };
        if (parsed.optional && typeof parsed.optional === 'object') {
          const migrated: Partial<Record<OptionalGridColField, boolean>> = {};
          for (const k of OPTIONAL_GRID_COL_FIELDS) {
            if (k in parsed.optional && typeof (parsed.optional as any)[k] === 'boolean') {
              migrated[k] = (parsed.optional as any)[k];
            }
          }
          if (Object.keys(migrated).length) setOptionalVisible((prev) => ({ ...prev, ...migrated }));
        }
        setOptionalColsHydrated(true);
        return;
      }
      const rawV1 = localStorage.getItem(LS_OPTIONAL_COLS_V1);
      if (rawV1) {
        const old = JSON.parse(rawV1) as Record<string, boolean>;
        const migrated: Partial<Record<OptionalGridColField, boolean>> = {};
        for (const k of OPTIONAL_GRID_COL_FIELDS) {
          if (k in old && typeof old[k] === 'boolean') migrated[k] = old[k];
        }
        if (Object.keys(migrated).length) setOptionalVisible((prev) => ({ ...prev, ...migrated }));
      }
    } catch {
      /* ignore */
    }
    setOptionalColsHydrated(true);
  }, []);

  useEffect(() => {
    if (!optionalColsHydrated || typeof window === 'undefined') return;
    try {
      localStorage.setItem(LS_GRID_COLS_V4, JSON.stringify({ version: 4, visibleOptional: optionalVisible }));
    } catch {
      /* ignore */
    }
  }, [optionalVisible, optionalColsHydrated]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const raw = localStorage.getItem(LS_SPEC_OPTIONAL_KEYS);
      if (raw) {
        const parsed = JSON.parse(raw) as Record<string, boolean>;
        if (parsed && typeof parsed === 'object') setOptionalSpecKeyVisible(parsed);
      }
    } catch {
      /* ignore */
    }
    setSpecKeyPrefsLoaded(true);
  }, []);

  useEffect(() => {
    if (!specKeyPrefsLoaded || typeof window === 'undefined') return;
    try {
      localStorage.setItem(LS_SPEC_OPTIONAL_KEYS, JSON.stringify(optionalSpecKeyVisible));
    } catch {
      /* ignore */
    }
  }, [optionalSpecKeyVisible, specKeyPrefsLoaded]);

  const { data: plans, isLoading, isError, error } = useQuery({
    queryKey: ['commercial-plans'],
    queryFn: ({ signal }) => apiGet<Plan[]>('/api/v1/commercial-planner/plans', { signal }),
    enabled: tab === 0,
  });

  const { data: lineupJobs, isLoading: lineupJobsLoading } = useQuery({
    queryKey: ['lineup-jobs'],
    queryFn: ({ signal }) => apiGet<LineupJob[]>('/api/v1/commercial-planner/lineup-jobs', { signal }),
    enabled: tab === 3 || (tab === 0 && addFromLineupOpen),
  });

  const { data: coverageLines, isLoading: coverageLoading } = useQuery({
    queryKey: ['lineup-coverage', lineupJobId],
    queryFn: ({ signal }) =>
      apiGet<LineupCoverageLine[]>(
        `/api/v1/commercial-planner/lineup-coverage?job_id=${lineupJobId}`,
        { signal }
      ),
    enabled: lineupJobId != null && tab === 3,
  });

  useEffect(() => {
    if (!addFromLineupOpen) return;
    if (addLineupJobId == null && lineupJobs && lineupJobs.length > 0) {
      setAddLineupJobId(lineupJobs[0].id);
    }
  }, [addFromLineupOpen, addLineupJobId, lineupJobs]);

  const { data: lineupModalLines, isFetching: lineupModalLoading } = useQuery({
    queryKey: ['lineup-coverage-modal', addLineupJobId],
    queryFn: ({ signal }) =>
      apiGet<LineupCoverageLine[]>(`/api/v1/commercial-planner/lineup-coverage?job_id=${addLineupJobId}`, { signal }),
    enabled: tab === 0 && addFromLineupOpen && addLineupJobId != null,
  });

  const { data: productGaps, isLoading: productGapsLoading } = useQuery({
    queryKey: ['lineup-product-gaps', lineupJobId],
    queryFn: ({ signal }) =>
      apiGet<LineupProductGap[]>(
        `/api/v1/commercial-planner/lineup-product-gaps?job_id=${lineupJobId}`,
        { signal }
      ),
    enabled: lineupJobId != null && tab === 3,
  });

  // Auto-select the newest job when lineup-jobs loads and no job has been chosen yet.
  // lineupJobs is ordered newest-first from the backend.
  useEffect(() => {
    if (lineupJobs && lineupJobs.length > 0 && lineupJobId == null) {
      setLineupJobId(lineupJobs[0].id);
    }
  }, [lineupJobs, lineupJobId]);

  // Reset line filter when the selected job changes (auto-select or manual pick).
  useEffect(() => {
    setCoverageFilter('');
  }, [lineupJobId]);

  const activePlanId = selectedPlanId ?? plans?.[0]?.id ?? null;
  const planCurrencyCode = useMemo(
    () => plans?.find((p) => p.id === activePlanId)?.currency_code ?? 'USD',
    [plans, activePlanId]
  );
  const activePlan = useMemo(() => plans?.find((p) => p.id === activePlanId) ?? null, [plans, activePlanId]);
  const { data: lines, isPending: linesPending } = useQuery({
    queryKey: ['commercial-plan-lines', activePlanId],
    queryFn: ({ signal }) => apiGet<PlanLine[]>(`/api/v1/commercial-planner/plans/${activePlanId}/lines`, { signal }),
    enabled: tab === 0 && activePlanId != null,
  });
  const linesLoadingOverlay = tab === 0 && activePlanId != null && linesPending;
  const { data: summary } = useQuery({
    queryKey: ['commercial-plan-summary', activePlanId],
    queryFn: ({ signal }) => apiGet<Summary>(`/api/v1/commercial-planner/plans/${activePlanId}/summary`, { signal }),
    enabled: tab === 0 && activePlanId != null,
  });
  const { data: suggestions } = useQuery({
    queryKey: ['commercial-plan-suggestions', activePlanId],
    queryFn: ({ signal }) => apiGet<SuggestionBundle[]>(`/api/v1/commercial-planner/plans/${activePlanId}/suggestions`, { signal }),
    enabled: tab === 0 && activePlanId != null,
  });

  const { data: planReadiness } = useQuery({
    queryKey: ['plan-readiness', activePlanId],
    queryFn: ({ signal }) =>
      apiGet<PlanReadiness>(`/api/v1/commercial-planner/plans/${activePlanId}/readiness`, { signal }),
    enabled: tab === 0 && activePlanId != null,
  });

  useEffect(() => {
    setRecalcFeedback(null);
  }, [activePlanId]);

  const { data: columnMetaData } = useQuery({
    queryKey: ['commercial-column-metadata', activePlanId],
    queryFn: ({ signal }) =>
      apiGet<ColumnMetadata>(
        `/api/v1/commercial-planner/plans/${activePlanId}/column-metadata`,
        { signal },
      ),
    enabled: activePlanId != null,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!columnMetaData?.spec_keys || !specKeyPrefsLoaded) return;
    setOptionalSpecKeyVisible((prev) => {
      const next = { ...prev };
      for (const k of Object.keys(columnMetaData.spec_keys)) {
        if (!(k in next)) next[k] = false;
      }
      return next;
    });
  }, [columnMetaData, specKeyPrefsLoaded]);

  const { data: lineupEvidence, isLoading: lineupEvidenceLoading } = useQuery({
    queryKey: ['lineup-evidence', lineProduct?.id],
    queryFn: ({ signal }) =>
      apiGet<LineupEvidence>(
        `/api/v1/commercial-planner/lineup-evidence?product_id=${lineProduct!.id}`,
        { signal }
      ),
    enabled: lineProduct != null && addLineOpen,
  });

  const lineById = useMemo(() => new Map((lines ?? []).map((l) => [l.id, l])), [lines]);

  const lineupDupKeySet = useMemo(() => {
    const s = new Set<string>();
    for (const l of lines ?? []) {
      s.add(`${l.customer_id}|${l.distributor_id}|${l.product_id}`);
    }
    return s;
  }, [lines]);

  const lineupFilteredRows = useMemo(() => {
    let r = lineupModalLines ?? [];
    if (lineupResolvedOnly) r = r.filter((x) => x.product_id != null);
    if (lineupUnresolvedCustOnly) r = r.filter((x) => x.has_unknown_customer);
    if (lineupWarningsOnly) r = r.filter((x) => x.has_warnings);
    const q = lineupModalFilter.trim().toLowerCase();
    if (q) {
      r = r.filter((x) =>
        [x.product_sku, x.product_name, x.model_raw, x.part_number_raw, x.customer_token].some((v) =>
          v != null && String(v).toLowerCase().includes(q)
        )
      );
    }
    return r;
  }, [lineupModalLines, lineupResolvedOnly, lineupUnresolvedCustOnly, lineupWarningsOnly, lineupModalFilter]);

  const runAddFromLineup = useCallback(async () => {
    if (activePlanId == null) return;
    setLineupBatchRunning(true);
    setLineupBatchSummary(null);
    let created = 0;
    let skippedDup = 0;
    let skippedIneligible = 0;
    let failed = 0;
    const rows = lineupFilteredRows.filter((x) => lineupSelectedIds.includes(x.id));
    const seen = new Set<string>(lineupDupKeySet);
    for (const row of rows) {
      const pid = row.product_id;
      const cid = row.header_customer_id ?? lineupFbCustomer?.id ?? null;
      const did = row.header_distributor_id ?? lineupFbDistributor?.id ?? null;
      if (pid == null) {
        skippedIneligible++;
        continue;
      }
      if (cid == null || did == null) {
        skippedIneligible++;
        continue;
      }
      const dupK = `${cid}|${did}|${pid}`;
      if (seen.has(dupK)) {
        skippedDup++;
        continue;
      }
      const splitTotal = monthSplitTotalUnits(row.month_split_json);
      const unitsRaw = row.quantity_units ?? splitTotal ?? 1;
      const units = Math.max(1, roundPlannerUnits(Number(unitsRaw)));
      const msrp = row.msrp_local;
      if (msrp == null || !(Number(msrp) > 0)) {
        skippedIneligible++;
        continue;
      }
      const body: Record<string, unknown> = {
        customer_id: cid,
        distributor_id: did,
        product_id: pid,
        target_units: units,
        target_srp_local: Number(msrp),
        promo_mix_pct: 0.5,
      };
      if (row.promo_price_local != null && Number(row.promo_price_local) > 0) {
        body.promo_srp_local = Number(row.promo_price_local);
      }
      try {
        await apiPost(`/api/v1/commercial-planner/plans/${activePlanId}/lines`, body);
        created++;
        seen.add(dupK);
      } catch {
        failed++;
      }
    }
    setLineupBatchSummary(
      `Created ${created}, skipped duplicates ${skippedDup}, skipped ineligible ${skippedIneligible}, failed ${failed}`
    );
    setLineupBatchRunning(false);
    await qc.invalidateQueries({ queryKey: ['commercial-plan-lines', activePlanId] });
    await qc.invalidateQueries({ queryKey: ['commercial-plan-summary', activePlanId] });
    await qc.invalidateQueries({ queryKey: ['commercial-plan-suggestions', activePlanId] });
  }, [
    activePlanId,
    lineupDupKeySet,
    lineupFbCustomer?.id,
    lineupFbDistributor?.id,
    lineupFilteredRows,
    lineupSelectedIds,
    qc,
  ]);

  const economicsComplete = useMemo(() => {
    if ((lines?.length ?? 0) === 0) return false;
    if ((summary?.flags?.length ?? 0) > 0) return false;
    return (lines ?? []).every((l) => {
      if (l.calc_sell_in_price_usd == null) return false;
      const tier = l.economics_line_trust;
      if (tier && tier !== 'ok') return false;
      if (!tier && lineHasBlockingEconomicsFlags(l)) return false;
      return true;
    });
  }, [lines, summary]);

  const selectedLine = selectedLineId != null ? (lineById.get(selectedLineId) ?? null) : null;

  const { data: selectedLineEvidence, isLoading: selectedLineEvidenceLoading } = useQuery({
    queryKey: ['lineup-evidence', selectedLine?.product_id],
    queryFn: ({ signal }) =>
      apiGet<LineupEvidence>(
        `/api/v1/commercial-planner/lineup-evidence?product_id=${selectedLine!.product_id}`,
        { signal }
      ),
    enabled: selectedLine != null && tab === 0,
  });

  const lineupSummary = useMemo(() => {
    if (!coverageLines) return null;
    const unresolvedTokens = new Set(
      coverageLines.filter((l) => l.has_unknown_customer && l.customer_token).map((l) => l.customer_token!)
    );
    return {
      total: coverageLines.length,
      resolvedProducts: coverageLines.filter((l) => l.product_id != null).length,
      unresolvedCustomers: unresolvedTokens.size,
      unresolvedCustomerRows: coverageLines.filter((l) => l.has_unknown_customer).length,
      warnings: coverageLines.filter((l) => l.has_warnings).length,
      // Commercial completeness
      msrpPresent: coverageLines.filter((l) => l.msrp_local != null).length,
      promoPresent: coverageLines.filter((l) => l.promo_price_local != null).length,
      dapPresent: coverageLines.filter((l) => l.dap_local != null).length,
      monthSplitPresent: coverageLines.filter((l) => l.month_split_json != null).length,
    };
  }, [coverageLines]);

  const unresolvedTokenChips = useMemo<Map<string, number>>(() => {
    if (!coverageLines) return new Map();
    const counts = new Map<string, number>();
    for (const ln of coverageLines) {
      if (ln.has_unknown_customer && ln.customer_token) {
        counts.set(ln.customer_token, (counts.get(ln.customer_token) ?? 0) + 1);
      }
    }
    return counts;
  }, [coverageLines]);

  const filteredCoverageLines = useMemo(() => {
    if (!coverageLines) return [];
    if (!coverageFilter.trim()) return coverageLines;
    const q = coverageFilter.trim().toLowerCase();
    return coverageLines.filter(
      (ln) =>
        (ln.product_sku?.toLowerCase().includes(q) ?? false) ||
        (ln.model_raw?.toLowerCase().includes(q) ?? false) ||
        (ln.part_number_raw?.toLowerCase().includes(q) ?? false) ||
        (ln.customer_token?.toLowerCase().includes(q) ?? false)
    );
  }, [coverageLines, coverageFilter]);

  const createPlan = useMutation({
    mutationFn: () => apiPost<{ id: number }>('/api/v1/commercial-planner/plans', planDraft),
    onSuccess: (res) => {
      setSelectedPlanId(res.id);
      setAddPlanOpen(false);
      setPlanDraft({
        plan_name: '',
        period_start: new Date().toISOString().slice(0, 10),
        owner: 'planner',
        currency_code: 'USD',
      });
      void qc.invalidateQueries({ queryKey: ['commercial-plans'] });
    },
  });
  const createLine = useMutation({
    mutationFn: () =>
      apiPost<{ id: number }>(`/api/v1/commercial-planner/plans/${activePlanId}/lines`, {
        customer_id: lineCustomer!.id,
        distributor_id: lineDistributor!.id,
        product_id: lineProduct!.id,
        target_units: Number(lineDraft.target_units),
        target_srp_local: Number(lineDraft.target_srp_local),
        promo_srp_local: lineDraft.promo_srp_local ? Number(lineDraft.promo_srp_local) : null,
        promo_mix_pct: Number(lineDraft.promo_mix_pct),
      }),
    onSuccess: () => {
      setAddLineOpen(false);
      setLineCustomer(null);
      setLineDistributor(null);
      setLineProduct(null);
      setLineDraft({
        target_units: '',
        target_srp_local: '',
        promo_srp_local: '',
        promo_mix_pct: '0.5',
      });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-lines', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-summary', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-suggestions', activePlanId] });
    },
  });
  const deleteLine = useMutation({
    mutationFn: (lineId: number) => apiDelete(`/api/v1/commercial-planner/lines/${lineId}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-plan-lines', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-summary', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-suggestions', activePlanId] });
    },
  });

  const deletePlan = useMutation({
    mutationFn: ({ planId, force }: { planId: number; force: boolean }) =>
      apiDelete(`/api/v1/commercial-planner/plans/${planId}?force=${force ? 'true' : 'false'}`),
    onSuccess: () => {
      setDeletePlanOpen(false);
      setSelectedPlanId(null);
      void qc.invalidateQueries({ queryKey: ['commercial-plans'] });
    },
  });
  const recalc = useMutation({
    mutationFn: () =>
      apiPost<{
        updated: number;
        plan_id: number;
        flags: string[];
        economics_trust?: string;
        economics_trust_note?: string | null;
        economics_plan_trust?: string;
        recalculate_trust_summary?: {
          lines_trusted_ok: number;
          lines_warning: number;
          lines_blocked: number;
          top_blocker_flags: string[];
        };
      }>(`/api/v1/commercial-planner/plans/${activePlanId}/recalculate`),
    onSuccess: (data) => {
      setRecalcFeedback({
        updated: data.updated,
        economics_trust: data.economics_trust ?? 'ok',
        economics_trust_note: data.economics_trust_note ?? null,
        economics_plan_trust: data.economics_plan_trust,
        recalculate_trust_summary: data.recalculate_trust_summary,
      });
      void qc.invalidateQueries({ queryKey: ['plan-readiness', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-lines', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-summary', activePlanId] });
    },
  });
  const applySuggestion = useMutation({
    mutationFn: (payload: { line_id: number; suggestion_type: string; value: unknown }) =>
      apiPost('/api/v1/commercial-planner/apply-suggestion', payload),
    onSuccess: () => {
      setSuggestionPreview(null);
      void qc.invalidateQueries({ queryKey: ['commercial-plan-lines', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-summary', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-suggestions', activePlanId] });
    },
  });

  const patchLineEntities = useMutation({
    mutationFn: (payload: { lineId: number; customer_id: number; distributor_id: number; product_id: number }) =>
      apiPatch(`/api/v1/commercial-planner/lines/${payload.lineId}`, {
        customer_id: payload.customer_id,
        distributor_id: payload.distributor_id,
        product_id: payload.product_id,
      }),
    onSuccess: () => {
      setEditLineOpen(false);
      setEditingLine(null);
      void qc.invalidateQueries({ queryKey: ['commercial-plan-lines', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-summary', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-suggestions', activePlanId] });
    },
  });

  const openEditLine = useCallback((row: PlanLine) => {
    setEditingLine(row);
    setEditCustomer({
      id: row.customer_id,
      customer_code: row.customer_code ?? '',
      customer_name: row.customer_name ?? '',
    });
    setEditDistributor({
      id: row.distributor_id,
      distributor_code: row.distributor_code ?? '',
      distributor_name: row.distributor_name ?? '',
    });
    setEditProduct({
      id: row.product_id,
      sku: row.product_sku ?? '',
      name: row.product_name ?? '',
    });
    setEditLineOpen(true);
  }, []);

  const onLineCell = useCallback(
    async (e: CellValueChangedEvent<PlanLine>) => {
      const lineId = e.data?.id;
      if (!lineId || e.oldValue === e.newValue || !e.colDef.field) return;
      const f = e.colDef.field;
      if (f === 'customer_id' || f === 'distributor_id' || f === 'product_id') return;
      let payloadValue: unknown = e.newValue;
      if (f === 'target_units' && e.newValue != null && e.newValue !== '') {
        payloadValue = roundPlannerUnits(Number(e.newValue));
      }
      await apiPatch(`/api/v1/commercial-planner/lines/${lineId}`, { [f]: payloadValue });
      await qc.invalidateQueries({ queryKey: ['commercial-plan-lines', activePlanId] });
      await qc.invalidateQueries({ queryKey: ['commercial-plan-summary', activePlanId] });
    },
    [activePlanId, qc]
  );

  const lineCols: ColDef<PlanLine>[] = useMemo(
    () => [
      {
        colId: 'customer_display',
        headerName: 'Customer',
        minWidth: 150,
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          const bits = [d.customer_code, d.customer_name].filter(Boolean);
          return bits.length ? bits.join(' — ') : `#${d.customer_id}`;
        },
      },
      {
        colId: 'distributor_display',
        headerName: 'Distributor',
        minWidth: 140,
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          const code = (d.distributor_code ?? '').trim().toUpperCase();
          if (code === 'UNASSIGNED') return 'Distributor unassigned';
          const bits = [d.distributor_code, d.distributor_name].filter(Boolean);
          return bits.length ? bits.join(' — ') : `#${d.distributor_id}`;
        },
      },
      {
        colId: 'product_sku_display',
        headerName: 'SKU',
        minWidth: 100,
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          return d.product_sku?.trim() ? d.product_sku : `#${d.product_id}`;
        },
      },
      {
        colId: 'product_part_number_display',
        headerName: 'Part #',
        minWidth: 95,
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          return d.product_part_number?.trim() ? d.product_part_number : '—';
        },
      },
      {
        colId: 'product_model_sales_display',
        headerName: 'Model / sales model',
        minWidth: 140,
        valueGetter: (p) => (p.data ? fmtModelSalesModel(p.data) : ''),
      },
      {
        colId: 'product_name_display',
        headerName: 'Product name',
        minWidth: 160,
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          return d.product_name?.trim() ? d.product_name : `#${d.product_id}`;
        },
      },
      {
        field: 'product_spec_warranty',
        headerName: 'Warranty',
        minWidth: 100,
        hide: !optionalVisible.product_spec_warranty,
        valueGetter: (p) => (p.data?.product_spec_warranty?.trim() ? p.data!.product_spec_warranty : '—'),
      },
      {
        field: 'product_spec_os',
        headerName: 'OS',
        minWidth: 90,
        hide: !optionalVisible.product_spec_os,
        valueGetter: (p) => (p.data?.product_spec_os?.trim() ? p.data!.product_spec_os : '—'),
      },
      {
        field: 'product_spec_colour',
        headerName: 'Colour',
        minWidth: 90,
        hide: !optionalVisible.product_spec_colour,
        valueGetter: (p) => (p.data?.product_spec_colour?.trim() ? p.data!.product_spec_colour : '—'),
      },
      {
        field: 'product_spec_cpu',
        headerName: 'CPU (spec)',
        minWidth: 110,
        hide: !optionalVisible.product_spec_cpu,
        valueGetter: (p) => (p.data?.product_spec_cpu?.trim() ? p.data!.product_spec_cpu : '—'),
      },
      {
        field: 'product_spec_processor',
        headerName: 'Processor (spec)',
        minWidth: 120,
        hide: !optionalVisible.product_spec_processor,
        valueGetter: (p) =>
          p.data?.product_spec_processor?.trim() ? p.data!.product_spec_processor : '—',
      },
      {
        field: 'product_category',
        headerName: 'Category',
        minWidth: 110,
        hide: !optionalVisible.product_category,
        valueGetter: (p) => p.data?.product_category?.trim() || '—',
      },
      {
        field: 'product_form_factor',
        headerName: 'Form factor',
        minWidth: 100,
        hide: !optionalVisible.product_form_factor,
        valueGetter: (p) => p.data?.product_form_factor?.trim() || '—',
      },
      {
        field: 'product_lifecycle_status',
        headerName: 'Lifecycle',
        minWidth: 95,
        hide: !optionalVisible.product_lifecycle_status,
        valueGetter: (p) => p.data?.product_lifecycle_status?.trim() || '—',
      },
      {
        field: 'product_line',
        headerName: 'Product line',
        minWidth: 110,
        hide: !optionalVisible.product_line,
        valueGetter: (p) => p.data?.product_line?.trim() || '—',
      },
      {
        field: 'product_series_name',
        headerName: 'Series',
        minWidth: 100,
        hide: !optionalVisible.product_series_name,
        valueGetter: (p) => p.data?.product_series_name?.trim() || '—',
      },
      {
        field: 'product_business_unit',
        headerName: 'Business unit',
        minWidth: 110,
        hide: !optionalVisible.product_business_unit,
        valueGetter: (p) => p.data?.product_business_unit?.trim() || '—',
      },
      {
        headerName: 'Edit',
        minWidth: 75,
        maxWidth: 80,
        sortable: false,
        filter: false,
        cellRenderer: ({ data }: { data: PlanLine }) =>
          data ? (
            <Button size="small" variant="outlined" onClick={() => openEditLine(data)}>
              Edit
            </Button>
          ) : null,
      },
      {
        field: 'target_units',
        headerName: 'Units',
        editable: true,
        type: 'numericColumn',
        minWidth: 85,
        valueFormatter: (p) => (p.value != null && p.value !== '' ? String(roundPlannerUnits(Number(p.value))) : ''),
      },
      { field: 'target_srp_local', headerName: `Customer-facing list price (${planCurrencyCode})`, editable: true, type: 'numericColumn', minWidth: 120 },
      { field: 'promo_srp_local', headerName: `Campaign / event price (${planCurrencyCode})`, editable: true, type: 'numericColumn', minWidth: 120 },
      {
        colId: 'economics_line_trust',
        headerName: 'Economics trust',
        minWidth: 130,
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          if (d.calc_sell_in_price_usd == null && (d.economics_line_trust == null || d.economics_line_trust === '')) {
            return 'Needs recalculation';
          }
          if (d.economics_line_trust) return String(d.economics_line_trust);
          if (lineHasBlockingEconomicsFlags(d)) return 'blocked';
          return 'ok';
        },
        cellRenderer: (p: ICellRendererParams<PlanLine>) => {
          const d = p.data;
          if (!d) return null;
          const raw =
            d.calc_sell_in_price_usd == null && (d.economics_line_trust == null || d.economics_line_trust === '')
              ? 'needs_recalc'
              : d.economics_line_trust ?? (lineHasBlockingEconomicsFlags(d) ? 'blocked' : 'ok');
          const label =
            raw === 'needs_recalc'
              ? 'Needs recalculation'
              : raw === 'blocked'
                ? 'Blocked'
                : raw === 'warning'
                  ? 'Warning'
                  : raw === 'ok'
                    ? 'Ok'
                    : String(raw);
          const color =
            raw === 'blocked' || raw === 'needs_recalc' ? 'error' : raw === 'warning' ? 'warning' : 'success';
          return <Chip size="small" label={label} color={color} variant="outlined" data-testid={`economics-trust-cell-${d.id}`} />;
        },
      },
      {
        field: 'calc_sell_in_price_local',
        headerName: `Estimated OEM/channel sell-in / unit (${planCurrencyCode})`,
        minWidth: 190,
        hide: !optionalVisible.calc_sell_in_price_local,
        valueGetter: (p) => {
          const v = p.data?.calc_sell_in_price_local;
          return v != null ? fmtCurrency(v) : '—';
        },
      },
      {
        field: 'calc_distributor_net_local',
        headerName: `Estimated distributor net / unit (${planCurrencyCode})`,
        minWidth: 240,
        hide: !optionalVisible.calc_distributor_net_local,
        valueGetter: (p) => {
          const v = p.data?.calc_distributor_net_local;
          return v != null ? fmtCurrency(v) : '—';
        },
      },
      {
        field: 'promo_mix_pct',
        headerName: 'Promo mix %',
        editable: true,
        type: 'numericColumn',
        minWidth: 100,
        hide: !optionalVisible.promo_mix_pct,
      },
      {
        field: 'effective_customer_margin_pct',
        headerName: 'Customer margin % (eff.)',
        hide: !optionalVisible.effective_customer_margin_pct,
        valueGetter: (p) => fmtMarginPct(p.data?.effective_customer_margin_pct ?? null),
      },
      {
        field: 'effective_customer_rebate_pct',
        headerName: 'Customer rebate % (eff.)',
        hide: !optionalVisible.effective_customer_rebate_pct,
        valueGetter: (p) => fmtMarginPct(p.data?.effective_customer_rebate_pct ?? null),
      },
      {
        field: 'effective_distributor_margin_pct',
        headerName: 'Distributor margin % (eff.)',
        hide: !optionalVisible.effective_distributor_margin_pct,
        valueGetter: (p) => fmtMarginPct(p.data?.effective_distributor_margin_pct ?? null),
      },
      {
        field: 'effective_vat_rate_pct',
        headerName: 'VAT % (eff.)',
        hide: !optionalVisible.effective_vat_rate_pct,
        valueGetter: (p) => fmtMarginPct(p.data?.effective_vat_rate_pct ?? null),
      },
      {
        field: 'effective_fx_rate_to_usd',
        headerName: `FX: ${planCurrencyCode} per 1 USD (eff.)`,
        hide: !optionalVisible.effective_fx_rate_to_usd,
        valueGetter: (p) => (p.data?.effective_fx_rate_to_usd != null ? String(p.data.effective_fx_rate_to_usd) : '—'),
      },
      {
        field: 'effective_reserve_total_pct',
        headerName: 'Reserve total % (eff.)',
        hide: !optionalVisible.effective_reserve_total_pct,
        valueGetter: (p) => fmtMarginPct(p.data?.effective_reserve_total_pct ?? null),
      },
      {
        field: 'effective_promo_reserve_split_pct',
        headerName: 'Promo reserve split % (eff.)',
        hide: !optionalVisible.effective_promo_reserve_split_pct,
        valueGetter: (p) => fmtMarginPct(p.data?.effective_promo_reserve_split_pct ?? null),
      },
      {
        field: 'effective_controlled_cost_usd_per_unit',
        headerName: `Controlled cost (${ECONOMICS_PIPELINE_CURRENCY}/u, eff.)`,
        hide: !optionalVisible.effective_controlled_cost_usd_per_unit,
        valueGetter: (p) => fmtCurrency(p.data?.effective_controlled_cost_usd_per_unit ?? null),
      },
      {
        field: 'calc_sell_in_price_usd',
        headerName: `Estimated OEM/channel sell-in (${ECONOMICS_PIPELINE_CURRENCY} / unit)`,
        minWidth: 170,
        hide: !optionalVisible.calc_sell_in_price_usd,
        valueFormatter: (p) => (p.value != null && p.value !== '' ? String(p.value) : '—'),
      },
      {
        field: 'calc_buy_price_usd',
        headerName: `Estimated distributor net (${ECONOMICS_PIPELINE_CURRENCY} / unit)`,
        minWidth: 240,
        hide: !optionalVisible.calc_buy_price_usd,
        valueFormatter: (p) => (p.value != null && p.value !== '' ? String(p.value) : '—'),
      },
      {
        field: 'calc_internal_gp_usd',
        headerName: `Estimated internal GP (${ECONOMICS_PIPELINE_CURRENCY}, total, after reserves)`,
        minWidth: 190,
        hide: !optionalVisible.calc_internal_gp_usd,
        tooltipValueGetter: (p) => economicsBlockingTooltip(p.data ?? undefined),
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          if (lineHasBlockingEconomicsFlags(d)) return '—';
          return d.calc_internal_gp_usd != null ? String(d.calc_internal_gp_usd) : '—';
        },
      },
      {
        field: 'calc_promo_reserve_usd',
        headerName: 'Promo reserve',
        minWidth: 120,
        hide: !optionalVisible.calc_promo_reserve_usd,
        tooltipValueGetter: (p) => economicsBlockingTooltip(p.data ?? undefined),
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          if (lineHasBlockingEconomicsFlags(d)) return '—';
          return d.calc_promo_reserve_usd != null ? String(d.calc_promo_reserve_usd) : '—';
        },
      },
      {
        field: 'calc_non_promo_reserve_usd',
        headerName: 'Non-promo reserve',
        minWidth: 140,
        hide: !optionalVisible.calc_non_promo_reserve_usd,
        tooltipValueGetter: (p) => economicsBlockingTooltip(p.data ?? undefined),
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          if (lineHasBlockingEconomicsFlags(d)) return '—';
          return d.calc_non_promo_reserve_usd != null ? String(d.calc_non_promo_reserve_usd) : '—';
        },
      },
      ...Object.keys(optionalSpecKeyVisible)
        .filter((k) => optionalSpecKeyVisible[k])
        .map((specKey) => ({
          colId: `spec_flat_${specKey}`,
          headerName: specKey,
          minWidth: 120,
          valueGetter: (p: { data?: PlanLine }) => {
            const flat = p.data?.product_specs_flat;
            if (!flat) return '—';
            const direct = flat[specKey];
            if (direct != null && String(direct).trim()) return String(direct);
            const lower = specKey.toLowerCase();
            const matchKey = Object.keys(flat).find((fk) => fk.toLowerCase() === lower);
            const v = matchKey ? flat[matchKey] : undefined;
            return v != null && String(v).trim() ? String(v) : '—';
          },
        })),
      {
        field: 'calc_flags',
        headerName: 'Issues',
        minWidth: 180,
        autoHeight: true,
        wrapText: true,
        cellRenderer: (p: ICellRendererParams<PlanLine>) => {
          const flags = p.data?.calc_flags ?? [];
          if (!flags.length) return '—';
          return (
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap component="span" sx={{ py: 0.25 }}>
              {flags.map((f) => (
                <Chip
                  key={f}
                  size="small"
                  label={fmtIssueChipLabel(f)}
                  title={`${fmtFlag(f)} (code: ${f})`}
                  color="warning"
                  variant="outlined"
                  data-testid={`issue-flag-${f}`}
                />
              ))}
            </Stack>
          );
        },
      },
      {
        headerName: 'Delete',
        minWidth: 75,
        maxWidth: 80,
        sortable: false,
        filter: false,
        cellRenderer: ({ data }: { data: PlanLine }) =>
          data ? (
            <Button size="small" color="error" onClick={() => void deleteLine.mutate(data.id)}>
              Delete
            </Button>
          ) : null,
      },
    ],
    [deleteLine, openEditLine, optionalSpecKeyVisible, optionalVisible, planCurrencyCode]
  );

  const lineGrid: GridOptions<PlanLine> = useMemo(
    () => ({
      singleClickEdit: true,
      loading: linesLoadingOverlay,
      enableBrowserTooltips: true,
      onCellValueChanged: (e) => void onLineCell(e),
      onRowClicked: (e) => {
        if (e.data) setSelectedLineId((prev) => (prev === e.data!.id ? null : e.data!.id));
      },
    }),
    [onLineCell, linesLoadingOverlay]
  );

  // ── Line detail panel (shown in right column when a line row is clicked) ─────
  const lineDetailPanel = selectedLine ? (
    <Paper sx={{ p: 2 }} data-testid="line-detail-panel">
      <Stack direction="row" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="subtitle1" sx={{ flex: 1 }}>
          Line detail
        </Typography>
        <Button size="small" sx={{ minWidth: 0, px: 0.5 }} onClick={() => setSelectedLineId(null)} title="Close">
          ✕
        </Button>
      </Stack>

      {/* Product / entity identity */}
      <Typography variant="body2" fontWeight={600} sx={{ mb: 0.25 }}>
        {selectedLine.product_sku ?? '—'}
        {selectedLine.product_name ? ` — ${selectedLine.product_name}` : ''}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.25 }}>
        Part #: {selectedLine.product_part_number?.trim() || '—'} · Model / sales model: {fmtModelSalesModel(selectedLine)}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        {[
          selectedLine.customer_code && `Cust: ${selectedLine.customer_code}`,
          selectedLine.distributor_code && `Dist: ${selectedLine.distributor_code}`,
        ]
          .filter(Boolean)
          .join(' · ')}
      </Typography>

      <Divider sx={{ mb: 1 }} />

      {/* Planning values */}
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Planning
      </Typography>
      <Stack spacing={0.25} sx={{ mb: 1 }}>
        <Typography variant="body2">Units: {selectedLine.target_units.toLocaleString()}</Typography>
        <Typography variant="body2">
          Customer-facing list price ({planCurrencyCode}): {fmtCurrency(selectedLine.target_srp_local)}
        </Typography>
        {selectedLine.promo_srp_local != null ? (
          <Typography variant="body2">
            Campaign / event price ({planCurrencyCode}): {fmtCurrency(selectedLine.promo_srp_local)}
          </Typography>
        ) : null}
        <Typography variant="body2">Promo mix: {(selectedLine.promo_mix_pct * 100).toFixed(0)}%</Typography>
      </Stack>

      <Divider sx={{ mb: 1 }} />

      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Economics waterfall
      </Typography>
      <LineEconomicsWaterfall
        line={{
          target_srp_local: selectedLine.target_srp_local,
          promo_srp_local: selectedLine.promo_srp_local,
          effective_vat_rate_pct: selectedLine.effective_vat_rate_pct,
          effective_fx_rate_to_usd: selectedLine.effective_fx_rate_to_usd,
          effective_customer_margin_pct: selectedLine.effective_customer_margin_pct,
          effective_customer_rebate_pct: selectedLine.effective_customer_rebate_pct,
          effective_distributor_margin_pct: selectedLine.effective_distributor_margin_pct,
          effective_reserve_total_pct: selectedLine.effective_reserve_total_pct,
          effective_promo_reserve_split_pct: selectedLine.effective_promo_reserve_split_pct,
          effective_controlled_cost_usd_per_unit: selectedLine.effective_controlled_cost_usd_per_unit,
          override_landed_cost_usd: selectedLine.override_landed_cost_usd,
          calc_sell_in_price_usd: selectedLine.calc_sell_in_price_usd,
          calc_buy_price_usd: selectedLine.calc_buy_price_usd,
          calc_promo_reserve_usd: selectedLine.calc_promo_reserve_usd,
          calc_non_promo_reserve_usd: selectedLine.calc_non_promo_reserve_usd,
          calc_internal_gp_usd: selectedLine.calc_internal_gp_usd,
          economics_line_trust: selectedLine.economics_line_trust,
          economics_line_trust_reasons: selectedLine.economics_line_trust_reasons,
          economics_field_provenance: selectedLine.economics_field_provenance,
          calc_flags: selectedLine.calc_flags,
        }}
        planCurrencyCode={planCurrencyCode}
        economicsReportingCurrency={ECONOMICS_PIPELINE_CURRENCY}
        formatTrustReason={fmtFlag}
        dapEvidenceLocal={selectedLineEvidence?.evidence?.dap_local ?? null}
      />
      {selectedLine.override_landed_cost_usd != null ? (
        <Chip
          size="small"
          label={`Override controlled cost: ${fmtMoneyWithCcy(selectedLine.override_landed_cost_usd, ECONOMICS_PIPELINE_CURRENCY)}`}
          color="info"
          variant="outlined"
          sx={{ mt: 0.75, mb: 0.5 }}
          data-testid="line-detail-cost-override"
        />
      ) : null}
      {(selectedLine.calc_flags ?? []).length > 0 ? (
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mb: 1 }} data-testid="line-detail-flags">
          {selectedLine.calc_flags!.map((f) => (
            <Chip key={f} size="small" label={fmtFlag(f)} color="warning" variant="outlined" />
          ))}
        </Stack>
      ) : null}

      {/* Lineup evidence for this product */}
      {selectedLineEvidenceLoading ? (
        <Typography variant="caption" color="text.secondary">
          Loading lineup evidence…
        </Typography>
      ) : selectedLineEvidence?.evidence ? (
        <>
          <Divider sx={{ mb: 1 }} />
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Lineup evidence{selectedLineEvidence.evidence.period_label ? ` — ${selectedLineEvidence.evidence.period_label}` : ''}
          </Typography>
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mb: 0.5 }} data-testid="line-detail-evidence">
            {selectedLineEvidence.evidence.msrp_local != null ? (
              <Chip size="small" label={`MSRP: ${fmtCurrency(selectedLineEvidence.evidence.msrp_local)}`} variant="outlined" />
            ) : null}
            {selectedLineEvidence.evidence.promo_price_local != null ? (
              <Chip
                size="small"
                label={`Promo: ${fmtCurrency(selectedLineEvidence.evidence.promo_price_local)}`}
                variant="outlined"
              />
            ) : null}
            {selectedLineEvidence.evidence.dap_local != null ? (
              <Chip
                size="small"
                label={`DAP evidence: ${fmtCurrency(selectedLineEvidence.evidence.dap_local)}`}
                variant="outlined"
                color="info"
                title="DAP is evidence in plan currency — not controlled cost or PM bottom"
              />
            ) : null}
            {selectedLineEvidence.evidence.total_quantity_units != null ? (
              <Chip
                size="small"
                label={`Lineup qty: ${selectedLineEvidence.evidence.total_quantity_units}`}
                variant="outlined"
              />
            ) : null}
          </Stack>
        </>
      ) : null}

      {/* Suggestions for this specific line */}
      {(() => {
        const bundle = suggestions?.find((b) => b.line_id === selectedLine.id);
        if (!bundle) return null;
        const activeSugs = bundle.suggestions
          .map((s, idx) => ({ s, key: `${bundle.line_id}-${s.type}-${idx}` }))
          .filter(({ key }) => !dismissed[key]);
        if (!activeSugs.length) return null;
        return (
          <>
            <Divider sx={{ mb: 1 }} />
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              Suggestions
            </Typography>
            {bundle._meta?.data_sources.lineup ? (
              <Chip
                size="small"
                label="Based on lineup evidence"
                color="info"
                variant="outlined"
                sx={{ mb: 0.75 }}
                data-testid="suggestion-lineup-source"
              />
            ) : bundle._meta?.data_sources && !bundle._meta.data_sources.sellout && !bundle._meta.data_sources.forecast ? (
              <Chip
                size="small"
                label="Limited data — suggestions may be weak"
                color="warning"
                variant="outlined"
                sx={{ mb: 0.75 }}
              />
            ) : null}
            <Stack spacing={0.75}>
              {activeSugs.map(({ s, key }) => {
                const ln = lineById.get(bundle.line_id);
                const preview = suggestionPreview?.key === key ? suggestionPreview : null;
                return (
                  <Paper key={key} variant="outlined" sx={{ p: 1 }} data-testid={`suggestion-card-${key}`}>
                    <Typography variant="caption" fontWeight={600} display="block">
                      {sugTypeLabel(s.type)} · {s.confidence} confidence
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                      {s.reason}
                    </Typography>
                    {preview ? (
                      <Box sx={{ mt: 0.5 }} data-testid="suggestion-apply-preview">
                        <Typography variant="caption" fontWeight={600} display="block" sx={{ mb: 0.5 }}>
                          Preview changes
                        </Typography>
                        {preview.rows.map((row) => (
                          <Typography key={row.label} variant="caption" display="block">
                            {row.label}: {row.from} → {row.to}
                          </Typography>
                        ))}
                        {preview.roundNote ? (
                          <Typography variant="caption" color="info.main" display="block" sx={{ mt: 0.5 }}>
                            {preview.roundNote}
                          </Typography>
                        ) : null}
                        <Stack direction="row" spacing={0.75} sx={{ mt: 1 }}>
                          <Button
                            size="small"
                            variant="contained"
                            data-testid="suggestion-confirm-apply"
                            disabled={applySuggestion.isPending}
                            onClick={() =>
                              applySuggestion.mutate({
                                line_id: preview.lineId,
                                suggestion_type: preview.suggestionType,
                                value: preview.applyValue,
                              })
                            }
                          >
                            Confirm apply
                          </Button>
                          <Button size="small" onClick={() => setSuggestionPreview(null)} disabled={applySuggestion.isPending}>
                            Cancel
                          </Button>
                        </Stack>
                      </Box>
                    ) : (
                      <Stack direction="row" spacing={0.75}>
                        <Button
                          size="small"
                          variant="contained"
                          data-testid="suggestion-apply-open-preview"
                          disabled={!ln || applySuggestion.isPending}
                          onClick={() => {
                            if (!ln) return;
                            setSuggestionPreview(buildSuggestionPreview(ln, s, key));
                          }}
                        >
                          Apply
                        </Button>
                        <Button size="small" onClick={() => setDismissed((prev) => ({ ...prev, [key]: true }))}>
                          Dismiss
                        </Button>
                      </Stack>
                    )}
                  </Paper>
                );
              })}
            </Stack>
          </>
        );
      })()}
    </Paper>
  ) : null;

  const plansPanel = (
    <>
      {/* ─── Single dominant grid Paper ─────────────────────────────────────── */}
      <Paper sx={{ p: 2, mb: 2 }}>
        {/* Plan selector + action bar */}
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }} flexWrap="wrap" useFlexGap>
          {isLoading ? (
            <Typography variant="body2" color="text.secondary">
              Loading plans…
            </Typography>
          ) : isError ? (
            <Typography variant="body2" color="error">
              Failed to load plans.{' '}
              <Button size="small" onClick={() => void qc.invalidateQueries({ queryKey: ['commercial-plans'] })}>
                Retry
              </Button>
            </Typography>
          ) : (plans ?? []).length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No plans yet — create one to start.
            </Typography>
          ) : (
            (plans ?? []).map((p) => (
              <Chip
                key={p.id}
                label={`${p.plan_name} (${p.status})`}
                color={activePlanId === p.id ? 'primary' : 'default'}
                variant={activePlanId === p.id ? 'filled' : 'outlined'}
                onClick={() => setSelectedPlanId(p.id)}
                clickable
                size="small"
              />
            ))
          )}
          <Button size="small" variant="outlined" onClick={() => setAddPlanOpen(true)} sx={{ ml: 'auto' }}>
            + New plan
          </Button>
          {activePlan?.status === 'draft' && (
            <Button
              size="small"
              variant="outlined"
              color="error"
              data-testid="delete-plan-btn"
              onClick={() => setDeletePlanOpen(true)}
            >
              Delete plan
            </Button>
          )}
          <Button size="small" variant="contained" onClick={() => setAddLineOpen(true)} disabled={activePlanId == null}>
            Add line
          </Button>
          <Button
            size="small"
            variant="outlined"
            data-testid="add-from-lineup-btn"
            onClick={() => {
              setLineupBatchSummary(null);
              setLineupSelectedIds([]);
              setLineupModalFilter('');
              setLineupResolvedOnly(false);
              setLineupUnresolvedCustOnly(false);
              setLineupWarningsOnly(false);
              setAddFromLineupOpen(true);
            }}
            disabled={activePlanId == null}
          >
            Add from lineup
          </Button>
          <Button size="small" variant="outlined" onClick={() => recalc.mutate()} disabled={activePlanId == null || recalc.isPending}>
            Recalculate
          </Button>
          <Button
            size="small"
            variant="outlined"
            data-testid="add-product-set-btn"
            onClick={() => setAddProductSetOpen(true)}
            disabled={activePlanId == null}
          >
            Add product set
          </Button>
          <Button
            size="small"
            variant="outlined"
            data-testid="column-manager-btn"
            onClick={() => setColumnSelectorOpen(true)}
            disabled={activePlanId == null}
          >
            Planner line columns
          </Button>
        </Stack>

        {recalcFeedback ? (
          <Alert
            severity={
              recalcFeedback.economics_plan_trust === 'blocked' ||
              (recalcFeedback.recalculate_trust_summary?.lines_blocked ?? 0) > 0
                ? 'error'
                : recalcFeedback.economics_plan_trust === 'warning' ||
                    recalcFeedback.economics_trust === 'low' ||
                    recalcFeedback.economics_trust === 'attention'
                  ? 'warning'
                  : 'success'
            }
            sx={{ mb: 1 }}
            data-testid="recalculate-trust-banner"
            onClose={() => setRecalcFeedback(null)}
          >
            <Typography variant="body2" fontWeight={600} component="div">
              Recalculate complete — {recalcFeedback.updated} line{recalcFeedback.updated !== 1 ? 's' : ''} updated
            </Typography>
            {recalcFeedback.recalculate_trust_summary ? (
              <Typography variant="body2" component="div" data-testid="recalculate-trust-summary" sx={{ mt: 0.5 }}>
                Trusted ok: {recalcFeedback.recalculate_trust_summary.lines_trusted_ok} · Warning / review:{' '}
                {recalcFeedback.recalculate_trust_summary.lines_warning} · Blocked / untrusted:{' '}
                {recalcFeedback.recalculate_trust_summary.lines_blocked}
                {recalcFeedback.recalculate_trust_summary.top_blocker_flags?.length ? (
                  <span>
                    {' '}
                    — Top blockers:{' '}
                    {recalcFeedback.recalculate_trust_summary.top_blocker_flags
                      .map((f) => fmtIssueChipLabel(f))
                      .join(', ')}
                  </span>
                ) : null}
              </Typography>
            ) : null}
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
              Plan line economics tier (aggregate): <strong>{recalcFeedback.economics_plan_trust ?? '—'}</strong>.
              {recalcFeedback.economics_trust === 'low'
                ? ' Recalculate completed, but economics trust is low until readiness and line assumptions are clean.'
                : ''}
              {recalcFeedback.economics_trust === 'attention'
                ? ' Review line trust chips, Issues flags, and distributor assignment before treating totals as decision-grade.'
                : ''}
              {recalcFeedback.economics_trust === 'ok' && recalcFeedback.economics_plan_trust === 'ok'
                ? ' Numbers were refreshed — this does not automatically mean every line is commercially valid without checking trust and flags.'
                : ''}
            </Typography>
            {recalcFeedback.economics_trust_note ? (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                {recalcFeedback.economics_trust_note}
              </Typography>
            ) : null}
          </Alert>
        ) : null}

        {/* Current lineups section */}
        <CurrentLineupSection
          activePlanId={activePlanId}
          planLineCount={activePlan?.line_count ?? 0}
          planCountryCode={activePlan?.country_code ?? null}
          planCurrencyCode={activePlan?.currency_code ?? null}
          onStagedLineupSummary={setStagedLineupSummary}
          onSyncComplete={({ planId, caseId }) => {
            void qc.invalidateQueries({ queryKey: ['commercial-plan-lines', planId] });
            void qc.invalidateQueries({ queryKey: ['commercial-plan-summary', planId] });
            void qc.invalidateQueries({ queryKey: ['commercial-column-metadata', planId] });
            void qc.invalidateQueries({ queryKey: ['commercial-plans'] });
            void qc.invalidateQueries({ queryKey: ['plan-readiness', planId] });
            void qc.invalidateQueries({ queryKey: ['commercial-lineup-case-lines', caseId] });
          }}
        />

        {/* Readiness panel */}
        {planReadiness && (
          <Box sx={{ mb: 1 }} data-testid="plan-readiness-panel">
            <Alert severity="info" sx={{ mb: 0.75, py: 0.5 }} data-testid="readiness-trust-intro">
              <Typography variant="body2" component="div" sx={{ mb: 0.25 }}>
                <strong>Readiness vs recalculate vs trust</strong>
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                Readiness counts missing or invalid defaults before you run the calculator. <strong>Recalculate</strong>{' '}
                refreshes persisted line outputs and returns a trust summary (ok / warning / blocked). Line trust and the
                economics waterfall explain which inputs were overrides, defaults, placeholders, or evidence — so
                outputs are never implied to be commercially valid when flags say otherwise.
              </Typography>
            </Alert>
            {planReadiness.missing_sku_assumption > 0 && (
              <Alert severity="warning" sx={{ mb: 0.5, py: 0.5 }}>
                <Typography variant="body2" component="div" sx={{ mb: 0.5 }}>
                  <strong>SKU assumption missing</strong> ({planReadiness.missing_sku_assumption} line
                  {planReadiness.missing_sku_assumption !== 1 ? 's' : ''}) — add controlled cost / VAT / FX / reserves
                  before economics can calculate.
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
                  Add SKU controlled cost assumptions in Planner defaults. These assumptions feed Commercial Planner
                  economics and are not populated from DAP.
                </Typography>
                <Button size="small" variant="outlined" onClick={() => setTab(1)} data-testid="readiness-open-planner-defaults-sku">
                  Open Planner defaults (SKU assumptions)
                </Button>
              </Alert>
            )}
            {planReadiness.missing_customer_term > 0 && (
              <Alert severity="warning" sx={{ mb: 0.5, py: 0.5 }}>
                <Typography variant="body2" component="div" sx={{ mb: 0.5 }}>
                  <strong>Customer terms missing</strong> ({planReadiness.missing_customer_term} line
                  {planReadiness.missing_customer_term !== 1 ? 's' : ''}).
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
                  Configure customer terms on the Customer page or bulk edit in Planner defaults.
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <MuiLink component={Link} href="/admin/customers" underline="hover" data-testid="readiness-link-customer-admin">
                    Customer admin
                  </MuiLink>
                  <Button size="small" variant="outlined" onClick={() => setTab(1)} data-testid="readiness-open-planner-defaults-customer">
                    Planner defaults (customer terms)
                  </Button>
                </Stack>
              </Alert>
            )}
            {planReadiness.missing_distributor_term > 0 && (
              <Alert severity="warning" sx={{ mb: 0.5, py: 0.5 }}>
                <Typography variant="body2" component="div" sx={{ mb: 0.5 }}>
                  <strong>Distributor terms missing</strong> ({planReadiness.missing_distributor_term} line
                  {planReadiness.missing_distributor_term !== 1 ? 's' : ''}).
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
                  Configure distributor terms on the Distributor page or bulk edit in Planner defaults.
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <MuiLink component={Link} href="/admin/distributors" underline="hover" data-testid="readiness-link-distributor-admin">
                    Distributor admin
                  </MuiLink>
                  <Button size="small" variant="outlined" onClick={() => setTab(1)} data-testid="readiness-open-planner-defaults-distributor">
                    Planner defaults (distributor terms)
                  </Button>
                </Stack>
              </Alert>
            )}
            {(planReadiness.invalid_controlled_cost ?? 0) > 0 && (
              <Alert severity="warning" sx={{ mb: 0.5, py: 0.5 }} data-testid="readiness-invalid-controlled-cost">
                <Typography variant="body2" component="div" sx={{ mb: 0.5 }}>
                  <strong>Invalid controlled cost</strong> ({planReadiness.invalid_controlled_cost} line
                  {(planReadiness.invalid_controlled_cost ?? 0) !== 1 ? 's' : ''}) — SKU assumption exists but PM bottom /
                  controlled cost is missing, zero, or negative. Fix in Planner defaults or Product admin.
                </Typography>
                <Button size="small" variant="outlined" onClick={() => setTab(1)} data-testid="readiness-open-planner-defaults-sku-invalid">
                  Open Planner defaults (SKU economics)
                </Button>
              </Alert>
            )}
            {(planReadiness.invalid_fx ?? 0) > 0 && (
              <Alert severity="warning" sx={{ mb: 0.5, py: 0.5 }} data-testid="readiness-invalid-fx">
                <Typography variant="body2" component="div" sx={{ mb: 0.5 }}>
                  <strong>Invalid FX on SKU assumption</strong> ({planReadiness.invalid_fx} line
                  {(planReadiness.invalid_fx ?? 0) !== 1 ? 's' : ''}) — FX must be plan/local currency units per 1 USD,
                  positive.
                </Typography>
                <Button size="small" variant="outlined" onClick={() => setTab(1)} data-testid="readiness-open-planner-defaults-sku-invalid-fx">
                  Open Planner defaults (SKU economics)
                </Button>
              </Alert>
            )}
            {(planReadiness.invalid_vat ?? 0) > 0 && (
              <Alert severity="warning" sx={{ mb: 0.5, py: 0.5 }} data-testid="readiness-invalid-vat">
                <Typography variant="body2" component="div" sx={{ mb: 0.5 }}>
                  <strong>Invalid VAT on SKU assumption</strong> ({planReadiness.invalid_vat} line
                  {(planReadiness.invalid_vat ?? 0) !== 1 ? 's' : ''}) — use decimal fraction 0–1 (e.g. 0.15 for 15%).
                </Typography>
                <Button size="small" variant="outlined" onClick={() => setTab(1)} data-testid="readiness-open-planner-defaults-sku-invalid-vat">
                  Open Planner defaults (SKU economics)
                </Button>
              </Alert>
            )}
            {(planReadiness.invalid_reserve ?? 0) > 0 && (
              <Alert severity="warning" sx={{ mb: 0.5, py: 0.5 }} data-testid="readiness-invalid-reserve">
                <Typography variant="body2" component="div" sx={{ mb: 0.5 }}>
                  <strong>Invalid reserves on SKU assumption</strong> ({planReadiness.invalid_reserve} line
                  {(planReadiness.invalid_reserve ?? 0) !== 1 ? 's' : ''}) — reserve total and campaign/support split must
                  be valid decimals in 0–1.
                </Typography>
                <Button size="small" variant="outlined" onClick={() => setTab(1)} data-testid="readiness-open-planner-defaults-sku-invalid-reserve">
                  Open Planner defaults (SKU economics)
                </Button>
              </Alert>
            )}
            {(planReadiness.using_unassigned_distributor ?? 0) > 0 && (
              <Alert severity="info" sx={{ mb: 0.5, py: 0.5 }} data-testid="readiness-unassigned-distributor">
                <strong>UNASSIGNED distributor</strong> on {planReadiness.using_unassigned_distributor} line
                {(planReadiness.using_unassigned_distributor ?? 0) !== 1 ? 's' : ''} — economics may need a real
                distributor and terms before they are commercially trustworthy.
              </Alert>
            )}
            {planReadiness.ready && planReadiness.line_count > 0 && (
              <Alert severity="success" sx={{ mb: 0.5, py: 0.5 }}>
                All defaults present — press <strong>Recalculate</strong> to compute economics.
              </Alert>
            )}
          </Box>
        )}

        {/* Recalculate-needed banner */}
        {lines != null && lines.some((l) => l.calc_sell_in_price_usd == null) && (
          <Alert severity="info" sx={{ mb: 1, py: 0.5 }} data-testid="recalc-needed-banner">
            Some lines have no calculated economics — press <strong>Recalculate</strong> to compute.
          </Alert>
        )}

        {/* Grid + conditional line-detail sidebar */}
        {lines !== undefined && (lines?.length ?? 0) === 0 && stagedLineupSummary.lineCount > 0 && (
          <Alert severity="info" sx={{ mb: 1 }} data-testid="staged-lineup-banner">
            Current lineup rows are staged. Mark the case as Ready to sync, then use Sync to plan to create planner lines.
          </Alert>
        )}
        <Stack direction="row" spacing={2} alignItems="stretch">
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <EnterpriseDataGrid rowData={lines ?? []} columnDefs={lineCols} gridOptions={lineGrid} height={480} />
          </Box>
          {selectedLine && (
            <Box sx={{ flex: '0 0 420px', width: 420, minWidth: 320 }}>{lineDetailPanel}</Box>
          )}
        </Stack>
      </Paper>

      {/* ─── Plan summary strip (below grid, trust-guarded) ─────────────────── */}
      {activePlanId != null && (
        <Paper sx={{ p: 1.5, mb: 1 }} data-testid="plan-summary-panel">
          {lines === undefined ? (
            <Typography variant="body2" color="text.secondary" data-testid="plan-summary-loading">
              Loading plan…
            </Typography>
          ) : (
          <Stack direction="row" spacing={3} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="body2">
              <strong>Lines:</strong> {summary?.line_count ?? lines.length}
            </Typography>
            <Typography variant="body2">
              <strong>Units:</strong>{' '}
              {summary?.total_units ?? lines.reduce((acc, l) => acc + (l.target_units ?? 0), 0)}
            </Typography>
            {economicsComplete ? (
              <>
                <Typography variant="body2">
                  <strong>Estimated internal GP ({ECONOMICS_PIPELINE_CURRENCY}, total, after reserves):</strong>{' '}
                  {summary?.total_internal_gp_usd ?? 0}
                </Typography>
                <Typography variant="body2">
                  <strong>Promo reserve ({ECONOMICS_PIPELINE_CURRENCY}):</strong> {summary?.total_promo_reserve_usd ?? 0}
                </Typography>
                <Typography variant="body2">
                  <strong>Non-promo reserve ({ECONOMICS_PIPELINE_CURRENCY}):</strong>{' '}
                  {summary?.total_non_promo_reserve_usd ?? 0}
                </Typography>
              </>
            ) : (
              <>
                <Chip
                  size="small"
                  label="Economics incomplete"
                  color="warning"
                  data-testid="economics-incomplete-chip"
                />
                {(summary?.flags ?? []).map((f) => (
                  <Chip key={f} size="small" label={fmtFlag(f)} color="warning" variant="outlined" />
                ))}
                <Typography variant="caption" color="text.secondary">
                  Complete missing defaults, then Recalculate.
                </Typography>
              </>
            )}
          </Stack>
          )}
        </Paper>
      )}

      {/* ─── Assisted suggestions (collapsible, default open) ───────────────── */}
      {activePlanId != null && (
        <Paper sx={{ p: 2, mb: 1 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: showSuggestions ? 1 : 0 }}>
            <Typography variant="subtitle2" sx={{ flex: 1 }}>
              Assisted suggestions
            </Typography>
            <Button
              size="small"
              onClick={() => setShowSuggestions((v) => !v)}
              data-testid="toggle-suggestions-btn"
            >
              {showSuggestions ? '▴ Hide' : '▾ Show'}
            </Button>
          </Stack>
          {showSuggestions && (
            <>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                Heuristics from history and forecasts — optional. Applying updates the line; use Recalculate when you
                need refreshed dollar outputs. Click a row in the grid to see per-line suggestions with evidence
                context.
              </Typography>
              <Stack spacing={1}>
                {(suggestions ?? []).flatMap((bundle) => {
                  const ln = lineById.get(bundle.line_id);
                  const label = lineEntitySummary(ln) || `Line #${bundle.line_id}`;
                  const isLineupBased = bundle._meta?.data_sources.lineup === true;
                  return bundle.suggestions
                    .map((s, idx) => ({ bundle, s, key: `${bundle.line_id}-${s.type}-${idx}` }))
                    .filter((x) => !dismissed[x.key])
                    .map(({ bundle, s, key }) => {
                      const ln = lineById.get(bundle.line_id);
                      const preview = suggestionPreview?.key === key ? suggestionPreview : null;
                      return (
                        <Paper key={key} variant="outlined" sx={{ p: 1 }} data-testid={`suggestion-card-main-${key}`}>
                          <Typography variant="body2">
                            <strong>{label}</strong> · {sugTypeLabel(s.type)} · {s.confidence}
                          </Typography>
                          {isLineupBased ? (
                            <Typography variant="caption" color="info.main" display="block">
                              Based on lineup evidence
                            </Typography>
                          ) : null}
                          <Typography variant="caption" color="text.secondary" display="block">
                            {s.reason}
                          </Typography>
                          {preview ? (
                            <Box sx={{ mt: 1 }} data-testid="suggestion-apply-preview-main">
                              <Typography variant="caption" fontWeight={600} display="block" sx={{ mb: 0.5 }}>
                                Preview changes
                              </Typography>
                              {preview.rows.map((row) => (
                                <Typography key={row.label} variant="caption" display="block">
                                  {row.label}: {row.from} → {row.to}
                                </Typography>
                              ))}
                              {preview.roundNote ? (
                                <Typography variant="caption" color="info.main" display="block" sx={{ mt: 0.5 }}>
                                  {preview.roundNote}
                                </Typography>
                              ) : null}
                              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                                <Button
                                  size="small"
                                  variant="contained"
                                  data-testid="suggestion-confirm-apply-main"
                                  disabled={applySuggestion.isPending}
                                  onClick={() =>
                                    applySuggestion.mutate({
                                      line_id: preview.lineId,
                                      suggestion_type: preview.suggestionType,
                                      value: preview.applyValue,
                                    })
                                  }
                                >
                                  Confirm apply
                                </Button>
                                <Button size="small" onClick={() => setSuggestionPreview(null)} disabled={applySuggestion.isPending}>
                                  Cancel
                                </Button>
                              </Stack>
                            </Box>
                          ) : (
                            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                              <Button
                                size="small"
                                variant="contained"
                                data-testid="suggestion-apply-open-preview-main"
                                disabled={!ln || applySuggestion.isPending}
                                onClick={() => {
                                  if (!ln) return;
                                  setSuggestionPreview(buildSuggestionPreview(ln, s, key));
                                }}
                              >
                                Apply
                              </Button>
                              <Button size="small" onClick={() => setDismissed((prev) => ({ ...prev, [key]: true }))}>
                                Dismiss
                              </Button>
                            </Stack>
                          )}
                        </Paper>
                      );
                    });
                })}
                {!suggestions?.length ? (
                  <Typography color="text.secondary">No suggestions available yet.</Typography>
                ) : null}
              </Stack>
            </>
          )}
        </Paper>
      )}

      {/* ─── Delete plan confirmation ──────────────────────────────────────── */}
      <Dialog open={deletePlanOpen} onClose={() => !deletePlan.isPending && setDeletePlanOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Delete plan</DialogTitle>
        <DialogContent>
          {activePlan && (
            <Stack spacing={1.5} sx={{ mt: 0.5 }}>
              <Alert severity="warning">
                <strong>Deleting plan: {activePlan.plan_name}</strong>
                <br />
                {(activePlan.line_count ?? 0) > 0
                  ? `This plan has ${activePlan.line_count} planner line(s). Deleting it will remove all lines and clear any current-lineup sync markers that reference this plan.`
                  : 'This empty draft plan will be permanently deleted.'}
              </Alert>
              {deletePlan.error && (
                <Alert severity="error">
                  {deletePlan.error instanceof Error ? deletePlan.error.message : 'Delete failed.'}
                </Alert>
              )}
              <Typography variant="body2" color="text.secondary">
                Only draft plans may be deleted. This action cannot be undone.
              </Typography>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeletePlanOpen(false)} disabled={deletePlan.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            data-testid="delete-plan-confirm-btn"
            disabled={deletePlan.isPending || activePlanId == null}
            onClick={() => {
              if (activePlanId == null) return;
              deletePlan.mutate({ planId: activePlanId, force: (activePlan?.line_count ?? 0) > 0 });
            }}
          >
            {deletePlan.isPending ? 'Deleting…' : 'Confirm delete'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={addPlanOpen} onClose={() => !createPlan.isPending && setAddPlanOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create commercial plan</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <TextField label="Plan name" value={planDraft.plan_name} onChange={(e) => setPlanDraft((p) => ({ ...p, plan_name: e.target.value }))} />
            <TextField label="Period start" value={planDraft.period_start} onChange={(e) => setPlanDraft((p) => ({ ...p, period_start: e.target.value }))} />
            <TextField label="Owner" value={planDraft.owner} onChange={(e) => setPlanDraft((p) => ({ ...p, owner: e.target.value }))} />
            <TextField
              label="Currency"
              value={planDraft.currency_code}
              onChange={(e) => setPlanDraft((p) => ({ ...p, currency_code: e.target.value }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddPlanOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => createPlan.mutate()} disabled={!planDraft.plan_name.trim()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={addLineOpen} onClose={() => !createLine.isPending && setAddLineOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add plan line</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 1 }}>
            Search each field below; pick a row from the list. Values are saved as proper foreign keys — you never need numeric IDs
            here.
          </Alert>
          <Stack spacing={1.5} sx={{ mt: 0 }}>
            <EntitySearchAutocomplete<CustomerPick>
              label="Customer"
              value={lineCustomer}
              onChange={setLineCustomer}
              fetchOptions={fetchCustomers}
              getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
              disabled={createLine.isPending}
              helperText="Type a few letters to search customers (code or name)."
            />
            <EntitySearchAutocomplete<DistributorPick>
              label="Distributor"
              value={lineDistributor}
              onChange={setLineDistributor}
              fetchOptions={fetchDistributors}
              getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
              disabled={createLine.isPending}
              helperText="Type to search distributors."
            />
            <EntitySearchAutocomplete<ProductPick>
              label="Product"
              value={lineProduct}
              onChange={setLineProduct}
              fetchOptions={fetchProducts}
              getOptionLabel={(o) => formatProductSearchOptionLabel(o)}
              disabled={createLine.isPending}
              helperText="Search by SKU, model, sales model, part number, or name — pick the row that matches your catalogue."
            />
            {lineProduct != null ? (
              <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'action.hover' }} data-testid="add-line-product-summary">
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
                  Selected product (review before save)
                </Typography>
                <Typography variant="body2">
                  <strong>SKU:</strong> {lineProduct.sku}
                </Typography>
                {lineProduct.part_number?.trim() ? (
                  <Typography variant="body2">
                    <strong>Part #:</strong> {lineProduct.part_number}
                  </Typography>
                ) : null}
                <Typography variant="body2">
                  <strong>Name:</strong> {lineProduct.name}
                </Typography>
                {(lineProduct.sales_model_name || lineProduct.model_name) && (
                  <Typography variant="body2">
                    <strong>Model / sales model:</strong>{' '}
                    {[lineProduct.sales_model_name, lineProduct.model_name].filter(Boolean).join(' · ')}
                  </Typography>
                )}
                {lineProduct.category?.trim() ? (
                  <Typography variant="body2">
                    <strong>Category:</strong> {lineProduct.category}
                  </Typography>
                ) : null}
                {lineProduct.form_factor?.trim() ? (
                  <Typography variant="body2">
                    <strong>Form factor:</strong> {lineProduct.form_factor}
                  </Typography>
                ) : null}
                {lineProduct.product_line?.trim() ? (
                  <Typography variant="body2">
                    <strong>Product line:</strong> {lineProduct.product_line}
                  </Typography>
                ) : null}
                {lineProduct.series_name?.trim() ? (
                  <Typography variant="body2">
                    <strong>Series:</strong> {lineProduct.series_name}
                  </Typography>
                ) : null}
                {lineProduct.lifecycle_status?.trim() ? (
                  <Typography variant="body2">
                    <strong>Lifecycle:</strong> {lineProduct.lifecycle_status}
                  </Typography>
                ) : null}
                {lineProduct.business_unit?.trim() ? (
                  <Typography variant="body2">
                    <strong>Business unit:</strong> {lineProduct.business_unit}
                  </Typography>
                ) : null}
                {lineProduct.specs_preview && Object.keys(lineProduct.specs_preview).length > 0 ? (
                  <Typography variant="body2" sx={{ mt: 0.5 }}>
                    <strong>Specs (preview):</strong>{' '}
                    {Object.entries(lineProduct.specs_preview)
                      .filter(([, v]) => v)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(' · ')}
                  </Typography>
                ) : null}
              </Paper>
            ) : null}
            {lineProduct != null ? (
              lineupEvidenceLoading ? (
                <Typography variant="caption" color="text.secondary">
                  Loading lineup evidence…
                </Typography>
              ) : lineupEvidence?.evidence ? (
                <Paper
                  variant="outlined"
                  sx={{ p: 1.5, bgcolor: 'action.hover' }}
                  data-testid="lineup-evidence-panel"
                >
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                    <strong>Lineup evidence</strong>
                    {lineupEvidence.evidence.period_label ? ` — ${lineupEvidence.evidence.period_label}` : ''}
                    {` · ${lineupEvidence.evidence.line_count} row${lineupEvidence.evidence.line_count !== 1 ? 's' : ''}`}
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    {lineupEvidence.evidence.msrp_local != null ? (
                      <Chip
                        size="small"
                        label={`MSRP/list: ${fmtCurrency(lineupEvidence.evidence.msrp_local)}`}
                        onClick={() =>
                          setLineDraft((p) => ({
                            ...p,
                            target_srp_local: String(lineupEvidence.evidence!.msrp_local),
                          }))
                        }
                        clickable
                        title="Click to use as customer-facing list price"
                        data-testid="use-msrp-as-srp"
                      />
                    ) : null}
                    {lineupEvidence.evidence.promo_price_local != null ? (
                      <Chip
                        size="small"
                        label={`Promo: ${fmtCurrency(lineupEvidence.evidence.promo_price_local)}`}
                        onClick={() =>
                          setLineDraft((p) => ({
                            ...p,
                            promo_srp_local: String(lineupEvidence.evidence!.promo_price_local),
                          }))
                        }
                        clickable
                        title="Click to use as campaign / event price"
                        data-testid="use-promo-as-srp"
                      />
                    ) : null}
                    {lineupEvidence.evidence.total_quantity_units != null ? (
                      <Chip
                        size="small"
                        label={`Lineup qty: ${lineupEvidence.evidence.total_quantity_units}`}
                        variant="outlined"
                      />
                    ) : null}
                    {lineupEvidence.evidence.dap_local != null ? (
                      <Chip
                        size="small"
                        label={`DAP evidence: ${fmtCurrency(lineupEvidence.evidence.dap_local)}`}
                        variant="outlined"
                        color="info"
                        title="DAP is source/local evidence only — not controlled cost or PM bottom"
                      />
                    ) : null}
                  </Stack>
                  <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 0.5 }}>
                    Click MSRP/list or promo chip to prefill. DAP is evidence only—not controlled cost.
                  </Typography>
                </Paper>
              ) : (
                <Typography variant="caption" color="text.secondary" data-testid="lineup-evidence-not-found">
                  No lineup evidence found for this product.
                </Typography>
              )
            ) : null}
            <Divider />
            <TextField label="Target units" value={lineDraft.target_units} onChange={(e) => setLineDraft((p) => ({ ...p, target_units: e.target.value }))} />
            <TextField
              label={`Customer-facing list price (${planCurrencyCode})`}
              value={lineDraft.target_srp_local}
              onChange={(e) => setLineDraft((p) => ({ ...p, target_srp_local: e.target.value }))}
            />
            <TextField
              label={`Campaign / event price (${planCurrencyCode}, optional)`}
              value={lineDraft.promo_srp_local}
              onChange={(e) => setLineDraft((p) => ({ ...p, promo_srp_local: e.target.value }))}
            />
            <TextField
              label="Promo mix pct (0-1)"
              value={lineDraft.promo_mix_pct}
              onChange={(e) => setLineDraft((p) => ({ ...p, promo_mix_pct: e.target.value }))}
            />
            {createLine.isError ? <Alert severity="error">Could not add line. Check selections and numbers.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddLineOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => void createLine.mutate()}
            disabled={
              !lineCustomer ||
              !lineDistributor ||
              !lineProduct ||
              !lineDraft.target_units ||
              !lineDraft.target_srp_local ||
              createLine.isPending
            }
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={addFromLineupOpen}
        onClose={() => {
          if (!lineupBatchRunning) setAddFromLineupOpen(false);
        }}
        maxWidth="lg"
        fullWidth
        data-testid="add-from-lineup-dialog"
      >
        <DialogTitle>Add from lineup</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Uses read-only lineup import rows. DAP and other lineup fields are never sent as controlled cost or
              landed_cost_usd.
            </Typography>
            <FormControl size="small" sx={{ minWidth: 280 }}>
              <InputLabel id="add-lineup-job-label">Lineup job</InputLabel>
              <Select
                labelId="add-lineup-job-label"
                label="Lineup job"
                value={addLineupJobId ?? ''}
                data-testid="add-lineup-job-select"
                onChange={(e) => setAddLineupJobId(Number(e.target.value) || null)}
                disabled={lineupJobsLoading || !(lineupJobs && lineupJobs.length)}
              >
                {(lineupJobs ?? []).map((j) => (
                  <MenuItem key={j.id} value={j.id}>
                    {j.period_label ?? j.file_name} — {j.line_count} lines
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              size="small"
              label="Filter rows"
              value={lineupModalFilter}
              onChange={(e) => setLineupModalFilter(e.target.value)}
              data-testid="lineup-modal-filter"
              fullWidth
            />
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={lineupResolvedOnly}
                    onChange={(e) => setLineupResolvedOnly(e.target.checked)}
                    data-testid="lineup-filter-resolved-only"
                  />
                }
                label="Resolved product only"
              />
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={lineupUnresolvedCustOnly}
                    onChange={(e) => setLineupUnresolvedCustOnly(e.target.checked)}
                    data-testid="lineup-filter-unresolved-customer"
                  />
                }
                label="Unresolved customer / token rows"
              />
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={lineupWarningsOnly}
                    onChange={(e) => setLineupWarningsOnly(e.target.checked)}
                    data-testid="lineup-filter-warnings-only"
                  />
                }
                label="Warnings only"
              />
            </Stack>
            <Typography variant="caption" color="text.secondary">
              Fallback customer / distributor apply when a row has no header customer or distributor id.
            </Typography>
            <EntitySearchAutocomplete<CustomerPick>
              label="Fallback customer"
              value={lineupFbCustomer}
              onChange={setLineupFbCustomer}
              fetchOptions={fetchCustomers}
              getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
            />
            <EntitySearchAutocomplete<DistributorPick>
              label="Fallback distributor"
              value={lineupFbDistributor}
              onChange={setLineupFbDistributor}
              fetchOptions={fetchDistributors}
              getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
            />
            {lineupModalLoading ? (
              <Typography variant="body2" color="text.secondary" data-testid="lineup-modal-loading">
                Loading lineup rows…
              </Typography>
            ) : (
              <Table size="small" data-testid="lineup-modal-table">
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox">
                      <Checkbox
                        size="small"
                        checked={
                          lineupFilteredRows.length > 0 &&
                          lineupFilteredRows.every((r) => lineupSelectedIds.includes(r.id))
                        }
                        indeterminate={
                          lineupSelectedIds.length > 0 &&
                          !lineupFilteredRows.every((r) => lineupSelectedIds.includes(r.id))
                        }
                        onChange={(e) => {
                          if (e.target.checked) {
                            setLineupSelectedIds(lineupFilteredRows.map((r) => r.id));
                          } else {
                            setLineupSelectedIds([]);
                          }
                        }}
                        inputProps={{ 'data-testid': 'lineup-modal-select-all' }}
                      />
                    </TableCell>
                    <TableCell>Row</TableCell>
                    <TableCell>Model / product</TableCell>
                    <TableCell>SKU</TableCell>
                    <TableCell>Part #</TableCell>
                    <TableCell>Customer</TableCell>
                    <TableCell>Distributor</TableCell>
                    <TableCell>Qty</TableCell>
                    <TableCell>MSRP</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {lineupFilteredRows.map((row) => (
                    <TableRow key={row.id} hover selected={lineupSelectedIds.includes(row.id)}>
                      <TableCell padding="checkbox">
                        <Checkbox
                          size="small"
                          checked={lineupSelectedIds.includes(row.id)}
                          onChange={(e) => {
                            setLineupSelectedIds((prev) => {
                              if (e.target.checked) return [...prev, row.id];
                              return prev.filter((id) => id !== row.id);
                            });
                          }}
                          data-testid={`lineup-row-cb-${row.id}`}
                        />
                      </TableCell>
                      <TableCell>{row.source_row_number}</TableCell>
                      <TableCell>{coverageLineupProductLabel(row)}</TableCell>
                      <TableCell>
                        <Typography variant="body2" fontFamily="monospace" component="span">
                          {row.product_sku ?? '—'}
                        </Typography>
                      </TableCell>
                      <TableCell>{row.part_number_raw?.trim() || '—'}</TableCell>
                      <TableCell>{coverageLineupCustomerCell(row)}</TableCell>
                      <TableCell>{coverageLineupDistributorCell(row)}</TableCell>
                      <TableCell>
                        {row.quantity_units ?? monthSplitTotalUnits(row.month_split_json) ?? '—'}
                      </TableCell>
                      <TableCell>{row.msrp_local != null ? fmtCurrency(row.msrp_local) : '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {lineupBatchSummary ? (
              <Alert severity="info" data-testid="lineup-batch-summary">
                {lineupBatchSummary}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddFromLineupOpen(false)} disabled={lineupBatchRunning}>
            Close
          </Button>
          <Button
            variant="contained"
            data-testid="lineup-modal-create"
            disabled={lineupBatchRunning || lineupSelectedIds.length === 0}
            onClick={() => void runAddFromLineup()}
          >
            Create plan lines
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={editLineOpen} onClose={() => !patchLineEntities.isPending && setEditLineOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Edit line entities</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 1 }}>
            Replace customer, distributor, or product with the same search-and-pick flow. Save, then use <strong>Recalculate</strong>{' '}
            on the plan if economics should refresh.
          </Alert>
          <Stack spacing={1.5} sx={{ mt: 0 }}>
            <EntitySearchAutocomplete<CustomerPick>
              label="Customer"
              value={editCustomer}
              onChange={setEditCustomer}
              fetchOptions={fetchCustomers}
              getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
              disabled={patchLineEntities.isPending}
              helperText="Search to replace the line’s customer."
            />
            <EntitySearchAutocomplete<DistributorPick>
              label="Distributor"
              value={editDistributor}
              onChange={setEditDistributor}
              fetchOptions={fetchDistributors}
              getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
              disabled={patchLineEntities.isPending}
              helperText="Search to replace the line’s distributor."
            />
            <EntitySearchAutocomplete<ProductPick>
              label="Product"
              value={editProduct}
              onChange={setEditProduct}
              fetchOptions={fetchProducts}
              getOptionLabel={(o) => formatProductSearchOptionLabel(o)}
              disabled={patchLineEntities.isPending}
              helperText="Search to replace the line’s product."
            />
            {patchLineEntities.isError ? <Alert severity="error">Update failed. Check that IDs exist.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditLineOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!editingLine || !editCustomer || !editDistributor || !editProduct || patchLineEntities.isPending}
            onClick={() => {
              if (!editingLine || !editCustomer || !editDistributor || !editProduct) return;
              void patchLineEntities.mutate({
                lineId: editingLine.id,
                customer_id: editCustomer.id,
                distributor_id: editDistributor.id,
                product_id: editProduct.id,
              });
            }}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );

  const lineupCoveragePanel = (
    <Stack spacing={2} data-testid="lineup-coverage-panel">
      {/* Job picker */}
      <FormControl size="small" sx={{ minWidth: 320, maxWidth: 480 }}>
        <InputLabel id="lineup-job-select-label">Lineup import job</InputLabel>
        <Select
          labelId="lineup-job-select-label"
          value={lineupJobId ?? ''}
          label="Lineup import job"
          inputProps={{ 'data-testid': 'lineup-job-select' }}
          onChange={(e) => setLineupJobId((e.target.value as number) || null)}
          disabled={lineupJobsLoading}
        >
          {(lineupJobs ?? []).map((j) => (
            <MenuItem key={j.id} value={j.id}>
              {j.period_label ?? j.file_name} — {j.line_count} line{j.line_count !== 1 ? 's' : ''}
            </MenuItem>
          ))}
        </Select>
        {lineupJobsLoading ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }} data-testid="lineup-jobs-loading">
            Loading import jobs…
          </Typography>
        ) : null}
      </FormControl>

      {/* Summary cards */}
      {lineupSummary ? (
        <Stack spacing={0.75} data-testid="lineup-summary-cards">
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={`Total: ${lineupSummary.total} lines`} />
            <Chip
              size="small"
              label={`Resolved products: ${lineupSummary.resolvedProducts} / ${lineupSummary.total}`}
              color="success"
              variant="outlined"
            />
            <Chip
              size="small"
              label={`Unresolved customers: ${lineupSummary.unresolvedCustomers} tokens, ${lineupSummary.unresolvedCustomerRows} rows`}
              color={lineupSummary.unresolvedCustomers > 0 ? 'warning' : 'default'}
              variant="outlined"
            />
            <Chip
              size="small"
              label={`Warnings: ${lineupSummary.warnings} rows`}
              color={lineupSummary.warnings > 0 ? 'error' : 'default'}
              variant="outlined"
            />
          </Stack>
          {/* Commercial completeness — price and month-split coverage */}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap data-testid="lineup-completeness-summary">
            <Chip
              size="small"
              label={`MSRP / list price: ${lineupSummary.msrpPresent} / ${lineupSummary.total}`}
              color={lineupSummary.msrpPresent < lineupSummary.total ? 'warning' : 'success'}
              variant="outlined"
            />
            <Chip
              size="small"
              label={`Promo price: ${lineupSummary.promoPresent} / ${lineupSummary.total}`}
              color={lineupSummary.promoPresent < lineupSummary.total ? 'warning' : 'success'}
              variant="outlined"
            />
            <Chip
              size="small"
              label={`DAP evidence: ${lineupSummary.dapPresent} / ${lineupSummary.total}`}
              variant="outlined"
            />
            <Chip
              size="small"
              label={`Month split: ${lineupSummary.monthSplitPresent} / ${lineupSummary.total}`}
              variant="outlined"
            />
          </Stack>
        </Stack>
      ) : null}

      {/* Unresolved customer token chips (has_unknown_customer only) */}
      {unresolvedTokenChips.size > 0 ? (
        <Box data-testid="lineup-coverage-unresolved-tokens">
          <Typography variant="caption" fontWeight={600} color="warning.main" sx={{ display: 'block', mb: 0.5 }}>
            Unresolved customer tokens
          </Typography>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {Array.from(unresolvedTokenChips.entries()).map(([token, count]) => (
              <Chip key={token} size="small" label={`${token} (${count})`} color="warning" variant="outlined" />
            ))}
          </Stack>
        </Box>
      ) : null}

      {/* Product defaults coverage */}
      {lineupJobId != null && (productGapsLoading || (productGaps && productGaps.length > 0)) ? (
        <Box data-testid="product-defaults-coverage">
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
            <Typography variant="subtitle2">Product defaults coverage</Typography>
            <Button
              size="small"
              variant="text"
              sx={{ minWidth: 0, p: 0, fontSize: '0.75rem', textTransform: 'none' }}
              onClick={() => setShowProductGaps((v) => !v)}
            >
              {showProductGaps ? 'Hide' : 'Show'}
            </Button>
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }} data-testid="product-gaps-caption">
            Product defaults coverage shows one row per product in this lineup and whether the planner
            already has SKU-level assumptions for that product. DAP is source/local evidence only—not controlled cost
            or PM bottom.
          </Typography>
          {showProductGaps ? (
            <>
              <Alert severity="info" icon={false} sx={{ mb: 1, py: 0.5 }}>
                <Typography variant="caption">
                  <strong>Evidence semantics:</strong> DAP (Distributor Acquisition Price) is the source import value. It
                  is <em>not</em> controlled cost (PM bottom) and must not be mapped to{' '}
                  <code>landed_cost_usd</code> without verification.
                </Typography>
              </Alert>
              {productGapsLoading ? (
                <Typography variant="body2" color="text.secondary" sx={{ pl: 1 }}>
                  Loading product coverage…
                </Typography>
              ) : (
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small" sx={{ minWidth: 700 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>SKU</TableCell>
                        <TableCell>Product</TableCell>
                        <TableCell>SKU assumption</TableCell>
                        <TableCell align="right">DAP evidence (src/local)</TableCell>
                        <TableCell align="right">Disti margin</TableCell>
                        <TableCell align="right">VAT evidence</TableCell>
                        <TableCell>Gaps</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(productGaps ?? []).map((pg) => (
                        <TableRow key={pg.product_id}>
                          <TableCell>{pg.product_sku}</TableCell>
                          <TableCell>{pg.product_name}</TableCell>
                          <TableCell>
                            <Chip
                              size="small"
                              label={pg.has_sku_assumption ? 'Exists' : 'Missing'}
                              color={pg.has_sku_assumption ? 'success' : 'warning'}
                              variant="outlined"
                            />
                          </TableCell>
                          <TableCell align="right">{fmtCurrency(pg.lineup_evidence.dap_local)}</TableCell>
                          <TableCell align="right">{fmtMarginPct(pg.lineup_evidence.disti_margin_pct)}</TableCell>
                          <TableCell align="right">
                            {pg.lineup_evidence.vat_pct != null ? fmtMarginPct(pg.lineup_evidence.vat_pct) : '—'}
                          </TableCell>
                          <TableCell>
                            {pg.assumption_gaps.length > 0
                              ? pg.assumption_gaps.map((g) => (
                                  <Chip
                                    key={g}
                                    size="small"
                                    label={g}
                                    color="warning"
                                    variant="outlined"
                                    sx={{ mr: 0.25, mb: 0.25 }}
                                  />
                                ))
                              : '—'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}
            </>
          ) : null}
        </Box>
      ) : null}

      {/* Line data table */}
      {lineupJobId == null ? (
        <Typography variant="body2" color="text.disabled" data-testid="lineup-empty-state">
          Select a lineup import job above to view loaded line data.
        </Typography>
      ) : coverageLoading ? (
        <Typography variant="body2" color="text.secondary">
          Loading…
        </Typography>
      ) : coverageLines ? (
        <Stack spacing={1}>
          <TextField
            size="small"
            label="Filter lines"
            placeholder="SKU, model, part #, customer token…"
            value={coverageFilter}
            onChange={(e) => setCoverageFilter(e.target.value)}
            sx={{ maxWidth: 360 }}
            inputProps={{ 'data-testid': 'coverage-filter' }}
          />
          {filteredCoverageLines.length > 0 ? (
            <Box sx={{ overflowX: 'auto' }} data-testid="lineup-coverage-table">
              <Table size="small" sx={{ minWidth: 1000 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Row</TableCell>
                    <TableCell>Product SKU</TableCell>
                    <TableCell>Model</TableCell>
                    <TableCell>Part #</TableCell>
                    <TableCell>Base unit</TableCell>
                    <TableCell>Customer</TableCell>
                    <TableCell align="right">Qty</TableCell>
                    <TableCell align="right">MSRP / list</TableCell>
                    <TableCell align="right">Promo price</TableCell>
                    <TableCell align="right">DAP evidence (src/local)</TableCell>
                    <TableCell align="right">Disti-reported cost evidence</TableCell>
                    <TableCell align="right">Disti %</TableCell>
                    <TableCell align="right">Rebate %</TableCell>
                    <TableCell align="right">VAT %</TableCell>
                    <TableCell>Month split</TableCell>
                    <TableCell>⚠</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filteredCoverageLines.map((ln) => (
                    <TableRow key={ln.id}>
                      <TableCell>{ln.source_row_number}</TableCell>
                      <TableCell>{ln.product_sku ?? '—'}</TableCell>
                      <TableCell>{ln.model_raw ?? '—'}</TableCell>
                      <TableCell>{ln.part_number_raw ?? '—'}</TableCell>
                      <TableCell>{ln.base_unit_raw ?? '—'}</TableCell>
                      <TableCell sx={ln.has_unknown_customer ? { color: 'warning.main' } : undefined}>
                        {ln.has_unknown_customer ? `⚠ ${ln.customer_token ?? '—'}` : (ln.customer_token ?? '—')}
                      </TableCell>
                      <TableCell align="right">{ln.quantity_units?.toLocaleString() ?? '—'}</TableCell>
                      <TableCell align="right">{fmtCurrency(ln.msrp_local)}</TableCell>
                      <TableCell align="right">{fmtCurrency(ln.promo_price_local)}</TableCell>
                      <TableCell align="right">{fmtCurrency(ln.dap_local)}</TableCell>
                      <TableCell align="right">{fmtCurrency(ln.disti_cost_local)}</TableCell>
                      <TableCell align="right" data-testid={`disti-margin-${ln.id}`}>
                        {fmtMarginPct(ln.disti_margin_pct)}
                      </TableCell>
                      <TableCell align="right">{fmtMarginPct(ln.rebate_pct)}</TableCell>
                      <TableCell align="right">{fmtMarginPct(ln.vat_pct)}</TableCell>
                      <TableCell>
                        {ln.month_split_json
                          ? Object.entries(ln.month_split_json)
                              .map(([m, v]) => `${m}: ${v}`)
                              .join(' / ')
                          : '—'}
                      </TableCell>
                      <TableCell>{ln.has_warnings ? '⚠' : ''}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          ) : coverageLines.length > 0 ? (
            <Typography variant="body2" color="text.disabled" data-testid="coverage-filter-no-matches">
              No lines match the current filter.
            </Typography>
          ) : (
            <Typography variant="body2" color="text.disabled" data-testid="lineup-no-lines">
              No lineup lines found for this job.
            </Typography>
          )}
        </Stack>
      ) : null}
    </Stack>
  );

  return (
    <>
      <PageHeader crumbs={[{ label: 'Commercial' }, { label: 'Planner' }]} title="Commercial planner" />
      <Box sx={{ mb: 2 }} data-testid="commercial-planner-workflow-guide">
        <Button
          size="small"
          variant="text"
          sx={{ textTransform: 'none', fontWeight: 400 }}
          onClick={() => setShowGuide((v) => !v)}
        >
          ℹ How this workspace fits together {showGuide ? '▴' : '▾'}
        </Button>
        {showGuide ? (
          <Alert severity="info" sx={{ mt: 0.5 }}>
            <Typography variant="body2" component="div" sx={{ '& ul': { m: 0, pl: 2.5 }, '& li': { mb: 0.5 } }}>
              <ul>
                <li>
                  <strong>Plans & lines</strong> — Pick a plan, then use <strong>Add line</strong> to open the builder. Customer,
                  distributor, and product are <strong>searchable pick lists</strong> (not raw IDs). Use <strong>Edit</strong> on a row
                  to change those entities. Edit units and prices in the grid; then press <strong>Recalculate</strong> to persist
                  economics. <em>Click any grid row to see line detail and per-line evidence in the right panel.</em>
                </li>
                <li>
                  <strong>Planner defaults</strong> — One row per customer, distributor, and SKU for margins, rebates, controlled
                  cost (PM bottom), VAT, FX, and reserves. Economics read these unless a line sets an explicit override. After
                  changing defaults, click <strong>Recalculate</strong> so stored line calcs match.
                </li>
                <li>
                  <strong>Data map</strong> — Read-only view of which commercial fields exist, where they are edited, and how
                  they relate to readiness and the calculator (including DAP as evidence only).
                </li>
                <li>
                  <strong>Assisted suggestions</strong> — Optional hints from history and forecasts. <strong>Apply</strong> writes the
                  suggestion to the line; recalculate again if you need updated dollars.
                </li>
              </ul>
            </Typography>
          </Alert>
        ) : null}
      </Box>
      <Paper sx={{ px: 2, pt: 1, mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} aria-label="Commercial planner sections">
          <Tab label="Plans & lines" id="commercial-planner-tab-plans" aria-controls="commercial-planner-panel-plans" />
          <Tab
            label="Planner defaults"
            id="commercial-planner-tab-defaults"
            aria-controls="commercial-planner-panel-defaults"
          />
          <Tab label="Data map" id="commercial-planner-tab-datamap" aria-controls="commercial-planner-panel-datamap" />
          <Tab
            label="Lineup coverage"
            id="commercial-planner-tab-lineup"
            aria-controls="commercial-planner-panel-lineup"
          />
        </Tabs>
      </Paper>
      <div
        role="tabpanel"
        id={
          tab === 0
            ? 'commercial-planner-panel-plans'
            : tab === 1
              ? 'commercial-planner-panel-defaults'
              : tab === 2
                ? 'commercial-planner-panel-datamap'
                : 'commercial-planner-panel-lineup'
        }
        aria-labelledby={
          tab === 0
            ? 'commercial-planner-tab-plans'
            : tab === 1
              ? 'commercial-planner-tab-defaults'
              : tab === 2
                ? 'commercial-planner-tab-datamap'
                : 'commercial-planner-tab-lineup'
        }
      >
        {tab === 0 ? (
          plansPanel
        ) : tab === 1 ? (
          <PlannerDefaultsMaintenance />
        ) : tab === 2 ? (
          <CommercialDataMap />
        ) : (
          lineupCoveragePanel
        )}
      </div>

      {/* Column selector modal (replaces Popover) */}
      <ColumnSelectorModal
        open={columnSelectorOpen}
        onClose={() => setColumnSelectorOpen(false)}
        lines={lines ?? []}
        optionalVisible={optionalVisible}
        specKeyVisible={optionalSpecKeyVisible}
        onSpecKeyToggle={(key, visible) =>
          setOptionalSpecKeyVisible((prev) => ({ ...prev, [key]: visible }))
        }
        onChange={(key, visible) => setOptionalVisible((prev) => ({ ...prev, [key]: visible }))}
        onReset={() => {
          setOptionalVisible(defaultOptionalVisibility());
          setOptionalSpecKeyVisible((prev) => {
            const next = { ...prev };
            for (const k of Object.keys(next)) next[k] = false;
            return next;
          });
        }}
        columnMeta={columnMetaData ?? null}
        onPreset={(preset) => {
          if (preset === 'planning') {
            setOptionalVisible(defaultOptionalVisibility());
          } else if (preset === 'product_spec') {
            setOptionalVisible((prev) => ({
              ...prev,
              product_spec_cpu: true,
              product_spec_processor: true,
              product_spec_warranty: true,
              product_spec_os: true,
              product_spec_colour: true,
            }));
            if (columnMetaData?.spec_keys) {
              const keys = Object.entries(columnMetaData.spec_keys)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8)
                .map(([k]) => k);
              setOptionalSpecKeyVisible((prev) => {
                const next = { ...prev };
                for (const k of keys) next[k] = true;
                return next;
              });
            }
          } else if (preset === 'commercial') {
            setOptionalVisible((prev) => ({
              ...prev,
              effective_customer_margin_pct: true,
              effective_customer_rebate_pct: true,
              effective_distributor_margin_pct: true,
              effective_vat_rate_pct: true,
              effective_fx_rate_to_usd: true,
              effective_reserve_total_pct: true,
              effective_promo_reserve_split_pct: true,
              effective_controlled_cost_usd_per_unit: true,
            }));
          } else if (preset === 'economics') {
            setOptionalVisible((prev) => ({
              ...prev,
              calc_sell_in_price_local: true,
              calc_distributor_net_local: true,
              calc_sell_in_price_usd: true,
              calc_internal_gp_usd: true,
              calc_buy_price_usd: true,
              calc_promo_reserve_usd: true,
              calc_non_promo_reserve_usd: true,
            }));
          }
        }}
      />

      {/* Add product set dialog */}
      <AddProductSetDialog
        open={addProductSetOpen}
        onClose={() => setAddProductSetOpen(false)}
        onCreated={() => {
          void qc.invalidateQueries({ queryKey: ['commercial-plan-lines', activePlanId] });
          void qc.invalidateQueries({ queryKey: ['commercial-plan-summary', activePlanId] });
        }}
        activePlanId={activePlanId}
        existingLines={lines ?? []}
      />
    </>
  );
}
