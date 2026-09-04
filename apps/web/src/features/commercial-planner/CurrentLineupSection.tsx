'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  FormHelperText,
  InputLabel,
  ListSubheader,
  Menu,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, GridOptions, ICellRendererParams } from 'ag-grid-community';
import NextLink from 'next/link';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { apiDelete, apiGet, apiPatch, apiPost, safeDisplayError } from '@/lib/api';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { EntitySearchAutocomplete } from './EntitySearchAutocomplete';
import {
  CustomerReconChips,
  ReconSummaryChips,
  type ReconCustomerSlice,
  type ReconSummary,
} from './lineupReconciliationDisplay';

function formatHttpErrorDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const d = detail as { message?: string; remediation?: string };
    const parts = [d.message, d.remediation].filter((x): x is string => Boolean(x));
    if (parts.length) return parts.join(' ');
  }
  if (Array.isArray(detail)) {
    return detail
      .map((e) =>
        typeof e === 'object' && e !== null && 'msg' in e
          ? String((e as { msg: unknown }).msg)
          : JSON.stringify(e),
      )
      .join('; ');
  }
  return 'unknown error';
}

// ── Types ─────────────────────────────────────────────────────────────────────

type SuggestedPo = {
  purchase_order_id: number;
  po_number: string;
  po_number_norm: string;
  distributor_id: number | null;
  distributor_code: string | null;
  distributor_name: string | null;
  matched_product_count: number;
  total_shipped_units: number;
  already_linked: boolean;
  status: string;
};

type LinkedPo = {
  purchase_order_id: number;
  po_number_raw: string;
  po_number_norm: string;
  distributor_id: number | null;
  status: string;
};

type SuggestedDistributor = {
  distributor_id: number;
  distributor_code: string | null;
  distributor_name: string | null;
  matched_product_count: number;
  total_shipped_units: number;
  po_count: number;
  already_assigned: boolean;
};

type SuggestedDistributorsResponse = {
  case_id: number;
  converged: boolean;
  converged_distributor_id: number | null;
  distinct_count: number;
  suggested_distributors: SuggestedDistributor[];
  already_assigned_distributor_ids: number[];
};

type CommercialLineupCase = {
  id: number;
  import_job_id: number | null;
  commercial_plan_id: number | null;
  file_name: string | null;
  period_label: string | null;
  country_code: string | null;
  currency_code: string | null;
  commercial_status: string;
  notes: string | null;
  accepted_at: string | null;
  accepted_by: string | null;
  line_count: number;
  iteration_number?: number;
  product_line?: string | null;
  inferred_period_start?: string | null;
  linked_pos?: LinkedPo[];
  po_count?: number;
  created_at: string | null;
  superseded_by_case_id?: number | null;
};

/** Case statuses where PO confirm is terminal — hide forward sync prompts. */
const STEWARD_WORK_OPEN_STATUSES = new Set([
  'draft_imported',
  'validated',
  'pending_review',
  'accepted',
  'po_pending',
  'po_issued',
  'in_fulfillment',
]);

const CLOSE_WORK_STATUSES = new Set(['po_pending', 'po_issued', 'in_fulfillment']);

const PO_LINKED_STATUSES = new Set(['po_pending', 'po_issued', 'in_fulfillment', 'received_closed', 'work_closed']);

type CommercialLineupLine = {
  id: number;
  case_id: number;
  source_row_number: number | null;
  product_id: number | null;
  product_sku: string | null;
  product_name: string | null;
  product_part_number: string | null;
  product_model_name: string | null;
  product_sales_model_name: string | null;
  customer_id: number | null;
  customer_code: string | null;
  customer_name: string | null;
  distributor_id: number | null;
  distributor_code: string | null;
  distributor_name: string | null;
  customer_token: string | null;
  distributor_token_raw: string | null;
  sku_raw: string | null;
  part_number_raw: string | null;
  model_raw: string | null;
  quantity_units: number | null;
  msrp_local: number | null;
  promo_price_evidence_local: number | null;
  dap_evidence_local: number | null;
  diagnostic_codes: string[];
  row_status: string;
  mapping_confidence?: number | null;
  dap_semantics_note?: string;
  staging_open_channel?: boolean;
  channel_route_uploaded_cell?: string | null;
  uploaded?: Record<string, unknown>;
  product_specs?: Record<string, unknown>;
  sync_eligible?: boolean;
  sync_skip_reason?: string | null;
  sync_skip_detail?: string | null;
  sync_ui_severity?: string | null;
  catalogue_category?: string | null;
  catalogue_form_factor?: string | null;
  catalogue_product_line?: string | null;
  catalogue_series_name?: string | null;
  catalogue_lifecycle_status?: string | null;
  catalogue_business_unit?: string | null;
  catalogue_marketing_name?: string | null;
  catalogue_ean?: string | null;
  catalogue_upc?: string | null;
  sync_customer_resolution_note?: string | null;
  synced_commercial_plan_line_id?: number | null;
  product_spec_cpu?: string | null;
  product_spec_processor?: string | null;
  /** Flattened, non-empty specs_json map — same keys as workbench-column-metadata catalogue_spec_keys. */
  product_specs_flat?: Record<string, string>;
  pricing_chain_json?: {
    outputs?: Record<string, number | null>;
  } | null;
  calc_dap_cost_currency?: number | null;
  calc_profit_total?: number | null;
  rebate_pct_evidence?: number | null;
  dealer_margin_pct_evidence?: number | null;
  distributor_margin_pct_evidence?: number | null;
  import_tax_pct_evidence?: number | null;
  vat_pct_evidence?: number | null;
  roe_evidence?: number | null;
};

type WorkbenchLineCounts = {
  all_lines: number;
  synced_to_planner: number;
  already_in_planner: number;
  ready_to_sync: number;
  blocked_from_sync: number;
  needs_resolution: number;
};

type CaseLinesResponse = {
  lines: CommercialLineupLine[];
  workbench_counts?: WorkbenchLineCounts;
  dap_semantics_note: string;
};

type WorkbenchColumnMetadata = {
  case_id: number;
  raw_columns: string[];
  parsed_fields: { id: string; group: string; label: string; field: string }[];
  catalogue_product_fields?: { id: string; group: string; label: string; field: string }[];
  catalogue_spec_keys: string[];
  /** Server-derived spec_json keys matching processor/CPU aliases (metadata-driven). */
  processor_spec_key_hints?: string[];
  sync_fields: { id: string; group: string; label: string; field: string }[];
  calc_fields?: { id: string; group: string; label: string; field: string }[];
};

const WB_STORAGE_V1 = 'cip.commercial-planner.currentLineupWorkbench.columns.v1';
const WB_STORAGE_V2 = 'cip.commercial-planner.currentLineupWorkbench.columns.v2';
const WB_STORAGE_V3 = 'cip.commercial-planner.currentLineupWorkbench.columns.v3';
const WB_STORAGE_V4 = 'cip.commercial-planner.currentLineupWorkbench.columns.v4';

/** Parsed evidence fields aligned with unified_lineup template (commercial chain, not CPU specs). */
const UNIFIED_LINEUP_PARSED_DEFAULTS = [
  'parsed:rebate_pct_evidence',
  'parsed:dealer_margin_pct_evidence',
  'parsed:distributor_margin_pct_evidence',
  'parsed:import_tax_pct_evidence',
  'parsed:vat_pct_evidence',
  'parsed:roe_evidence',
] as const;

/** Derived pricing chain columns (pricing_chain_json.outputs + persisted calc_* fields). */
const UNIFIED_LINEUP_CALC_DEFAULTS = [
  'calc:dealer_price',
  'calc:net_price',
  'calc:disti_cost',
  'calc:dap',
  'calc:profit',
] as const;

const UNIFIED_LINEUP_CATALOGUE_DEFAULTS = [
  'cat:product_model_name',
  'cat:product_spec_processor',
  'cat:catalogue_series_name',
  'cat:catalogue_product_line',
] as const;

/** Default visible columns for unified lineup workbench — commercial template first. */
function defaultUnifiedLineupWorkbenchIds(
  meta: WorkbenchColumnMetadata | undefined,
  hasPlan: boolean,
): string[] {
  const allow = mergeWorkbenchAllowedIds(meta, hasPlan);
  const core = defaultWorkbenchVisible(hasPlan).filter((id) => allow.has(id));
  const extras: string[] = [];
  for (const id of UNIFIED_LINEUP_PARSED_DEFAULTS) {
    if (allow.has(id)) extras.push(id);
  }
  for (const id of UNIFIED_LINEUP_CALC_DEFAULTS) {
    if (allow.has(id)) extras.push(id);
  }
  for (const id of UNIFIED_LINEUP_CATALOGUE_DEFAULTS) {
    if (allow.has(id)) extras.push(id);
  }
  const withoutSync = core.filter((id) => id !== 'sync');
  const msrpIdx = withoutSync.indexOf('msrp');
  const insertAt = msrpIdx >= 0 ? msrpIdx + 1 : withoutSync.length;
  const merged = [
    ...withoutSync.slice(0, insertAt),
    ...extras.filter((id) => !withoutSync.includes(id)),
    ...withoutSync.slice(insertAt),
  ];
  return hasPlan && allow.has('sync') ? [...merged, 'sync'] : merged;
}

const CORE_WORKBENCH_IDS = [
  'num',
  'product',
  'sku',
  'part',
  'cust',
  'dist',
  'units',
  'msrp',
  'promo',
  'dap',
  'issues',
  'sync',
] as const;

type CoreWorkbenchId = (typeof CORE_WORKBENCH_IDS)[number];

const CORE_WORKBENCH_LABELS: Record<CoreWorkbenchId, string> = {
  num: '#',
  product: 'Model / product',
  sku: 'SKU',
  part: 'Part #',
  cust: 'Customer',
  dist: 'Distributor',
  units: 'Units',
  msrp: 'MSRP / list',
  promo: 'Promo evidence',
  dap: 'DAP (evidence)',
  issues: 'Status / issues',
  sync: 'Sync preview (plan)',
};

function rawHeaderMatchesProcessorAliases(header: string): boolean {
  const n = header.toLowerCase().trim();
  if (!n) return false;
  const needles = ['processor', 'cpu', 'processor model', 'processor type'];
  return needles.some((t) => n === t || n.includes(t));
}

/** Optional column preset — processor/upload CPU specs (never auto-injected). */
function pickProcessorPresetWorkbenchIds(meta: WorkbenchColumnMetadata): string[] {
  const out: string[] = [];
  const rawColumns = meta.raw_columns ?? [];
  const byLower = new Map(rawColumns.map((c) => [c.toLowerCase(), c]));
  for (const pref of ['cpu', 'processor']) {
    const exact = byLower.get(pref);
    if (exact) out.push(`raw:${exact}`);
  }
  for (const c of rawColumns) {
    if (rawHeaderMatchesProcessorAliases(c) && !out.includes(`raw:${c}`)) out.push(`raw:${c}`);
  }
  const specKeySet = new Set(meta.catalogue_spec_keys ?? []);
  for (const k of meta.processor_spec_key_hints ?? []) {
    if (specKeySet.has(k) && !out.includes(`spec:${k}`)) out.push(`spec:${k}`);
  }
  return out;
}

function defaultWorkbenchVisible(hasPlan: boolean): string[] {
  const base = [
    'num',
    'product',
    'part',
    'cust',
    'dist',
    'units',
    'msrp',
    'promo',
    'dap',
    'issues',
  ];
  return hasPlan ? [...base, 'sync'] : base;
}

function mergeWorkbenchAllowedIds(meta: WorkbenchColumnMetadata | undefined, hasPlan: boolean): Set<string> {
  const s = new Set<string>([
    'num',
    'product',
    'sku',
    'part',
    'cust',
    'dist',
    'units',
    'msrp',
    'promo',
    'dap',
    'issues',
    'calc:dealer_price',
    'calc:net_price',
    'calc:disti_cost',
    'calc:dap',
    'calc:profit',
  ]);
  if (hasPlan) s.add('sync');
  if (!meta) return s;
  const rawCols = Array.isArray(meta.raw_columns) ? meta.raw_columns : [];
  for (const c of rawCols) s.add(`raw:${c}`);
  const parsed = Array.isArray(meta.parsed_fields) ? meta.parsed_fields : [];
  for (const p of parsed) s.add(p.id);
  const specKeys = Array.isArray(meta.catalogue_spec_keys) ? meta.catalogue_spec_keys : [];
  for (const k of specKeys) s.add(`spec:${k}`);
  const catFs = Array.isArray(meta.catalogue_product_fields) ? meta.catalogue_product_fields : [];
  for (const c of catFs) s.add(c.id);
  const syncFs = Array.isArray(meta.sync_fields) ? meta.sync_fields : [];
  for (const f of syncFs) s.add(f.id);
  const calcFs = Array.isArray(meta.calc_fields) ? meta.calc_fields : [];
  for (const c of calcFs) s.add(c.id);
  return s;
}

function readCaseWorkbenchStorage(caseId: number): string[] | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(WB_STORAGE_V4);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    const cases = (parsed as { cases?: Record<string, unknown> }).cases;
    if (!cases || typeof cases !== 'object') return null;
    const entry = cases[String(caseId)];
    if (!Array.isArray(entry) || !entry.every((x) => typeof x === 'string') || !entry.length) return null;
    return entry as string[];
  } catch {
    return null;
  }
}

function saveCaseWorkbenchStorage(caseId: number, cols: string[]): void {
  if (typeof window === 'undefined' || !cols.length) return;
  try {
    const raw = localStorage.getItem(WB_STORAGE_V4);
    let cases: Record<string, string[]> = {};
    if (raw) {
      const parsed = JSON.parse(raw) as { cases?: Record<string, string[]> };
      if (parsed?.cases && typeof parsed.cases === 'object') cases = { ...parsed.cases };
    }
    cases[String(caseId)] = cols;
    localStorage.setItem(WB_STORAGE_V4, JSON.stringify({ version: 1, cases }));
  } catch {
    /* ignore quota / private mode */
  }
}

function readInitialWorkbenchVisible(
  caseId: number | null,
  meta: WorkbenchColumnMetadata | undefined,
  hasPlan: boolean,
): string[] {
  const fallback = defaultUnifiedLineupWorkbenchIds(meta, hasPlan);
  if (caseId == null) return fallback;
  const stored = readCaseWorkbenchStorage(caseId);
  if (stored) return stored;
  return fallback;
}

const SPEC_KEY_HUMAN_LABELS: Record<string, string> = {
  cpu: 'CPU',
  cpu_model: 'CPU model',
  cpu_platform: 'CPU platform',
  cpu_segment: 'CPU segment',
  cpu_vendor: 'CPU vendor',
  processor: 'Processor',
  processor_model: 'Processor model',
  neural_processor: 'Neural processor',
  gpu: 'GPU',
  ram: 'RAM',
  storage: 'Storage',
  display: 'Display',
  display_size: 'Display size',
  product_line: 'Product line',
  sales_model: 'Sales model',
  model_name: 'Model name',
  os: 'OS',
  colour: 'Colour',
  warranty: 'Warranty',
  battery: 'Battery',
  weight: 'Weight',
};

function humanizeSpecKey(k: string): string {
  return SPEC_KEY_HUMAN_LABELS[k.toLowerCase()] ?? k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const CALC_COLUMN_LABELS: Record<string, string> = {
  'calc:dealer_price': 'Dealer price (calc)',
  'calc:net_price': 'Net price (calc)',
  'calc:disti_cost': 'Disti cost (calc)',
  'calc:dap': 'DAP (calc)',
  'calc:profit': 'Profit total (calc)',
};

const PCT_EVIDENCE_FIELDS = new Set([
  'rebate_pct_evidence',
  'dealer_margin_pct_evidence',
  'distributor_margin_pct_evidence',
  'import_tax_pct_evidence',
  'vat_pct_evidence',
]);

function formatPctEvidenceValue(value: unknown): string {
  if (value == null) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  const dp = pct >= 10 ? 1 : 2;
  const text = pct.toFixed(dp).replace(/\.?0+$/, '');
  return `${text}%`;
}

function formatMoneyWorkbenchValue(value: unknown): string {
  if (value == null) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function calcChainOutput(ln: CommercialLineupLine, outputKey: string): number | null {
  const chain = ln.pricing_chain_json;
  if (!chain || typeof chain !== 'object') return null;
  const outputs = (chain as { outputs?: Record<string, unknown> }).outputs;
  if (!outputs || typeof outputs !== 'object') return null;
  const raw = outputs[outputKey];
  if (raw == null) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function workbenchColumnLabel(colId: string, meta: WorkbenchColumnMetadata | undefined): string {
  if ((CORE_WORKBENCH_IDS as readonly string[]).includes(colId)) {
    return CORE_WORKBENCH_LABELS[colId as CoreWorkbenchId];
  }
  if (colId in CALC_COLUMN_LABELS) return CALC_COLUMN_LABELS[colId]!;
  if (colId.startsWith('calc:') && meta) {
    const calcFs = Array.isArray(meta.calc_fields) ? meta.calc_fields : [];
    const hit = calcFs.find((p) => p.id === colId);
    if (hit) return hit.label;
  }
  if (colId.startsWith('raw:')) return `Upload: ${colId.slice(4)}`;
  if (colId.startsWith('spec:')) {
    const k = colId.slice(5);
    return `Spec: ${humanizeSpecKey(k)}`;
  }
  if (colId.startsWith('cat:') && meta) {
    const cats = Array.isArray(meta.catalogue_product_fields) ? meta.catalogue_product_fields : [];
    const hit = cats.find((p) => p.id === colId);
    if (hit) return hit.label;
  }
  if (colId.startsWith('cat:')) return colId.replace('cat:', '').replace(/_/g, ' ');
  if (colId.startsWith('parsed:') && meta) {
    const parsed = Array.isArray(meta.parsed_fields) ? meta.parsed_fields : [];
    const hit = parsed.find((p) => p.id === colId);
    if (hit) return hit.label;
  }
  if (colId.startsWith('sync:') && meta) {
    const syncFs = Array.isArray(meta.sync_fields) ? meta.sync_fields : [];
    const hit = syncFs.find((p) => p.id === colId);
    if (hit) return hit.label;
  }
  if (colId.startsWith('parsed:')) return colId.replace('parsed:', '').replace(/_/g, ' ');
  if (colId.startsWith('sync:')) return colId.replace('sync:', '').replace(/_/g, ' ');
  return colId;
}

function formatParsedFieldForWorkbench(ln: CommercialLineupLine, field: string): string {
  const v = (ln as Record<string, unknown>)[field];
  if (v == null) return '—';
  if (PCT_EVIDENCE_FIELDS.has(field)) return formatPctEvidenceValue(v);
  if (Array.isArray(v)) return v.length ? JSON.stringify(v) : '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function formatSyncFieldForWorkbench(ln: CommercialLineupLine, field: string): string {
  const v = (ln as Record<string, unknown>)[field];
  if (v == null) return '—';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  return String(v);
}

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };

type EntityTokenCandidate = {
  token_norm: string;
  token_display: string;
  line_count: number;
  sample_line_ids: number[];
  case_ids?: number[];
  case_count?: number;
  token_source?: 'distributor_column' | 'open_channel_route';
};

type EntityResolutionCandidatesResponse = {
  case_id?: number;
  plan_id?: number | null;
  eligible_case_ids?: number[];
  eligible_case_count?: number;
  token_count?: number;
  customer_tokens: EntityTokenCandidate[];
  distributor_tokens: EntityTokenCandidate[];
};

const RESOLUTION_UI_STATUSES = STEWARD_WORK_OPEN_STATUSES;

function isSupersededCase(c: CommercialLineupCase): boolean {
  return c.commercial_status === 'superseded';
}

function lineupProductLabel(ln: CommercialLineupLine): string {
  const a =
    ln.product_sales_model_name?.trim() ||
    ln.product_model_name?.trim() ||
    ln.model_raw?.trim() ||
    ln.product_name?.trim() ||
    ln.product_sku?.trim() ||
    ln.sku_raw?.trim() ||
    ln.part_number_raw?.trim();
  return a || '—';
}

function lineupCustomerCell(ln: CommercialLineupLine): string {
  if (ln.staging_open_channel) {
    const code = (ln.customer_code ?? '').trim().toUpperCase();
    if (ln.customer_id != null && code === 'OPEN_CHANNEL') {
      const bits = [ln.customer_code, ln.customer_name].filter((x) => x?.trim());
      return bits.length ? `${bits.join(' — ')} (Open Channel account)` : 'Open Channel account';
    }
    const route = ln.channel_route_uploaded_cell?.trim();
    if (route) return `Open Channel · ${route} (end customer unassigned)`;
    return 'Open Channel (end customer unassigned)';
  }
  if (ln.customer_id != null) {
    const bits = [ln.customer_code, ln.customer_name].filter((x) => x?.trim());
    if (bits.length) return bits.join(' — ');
  }
  const t = ln.customer_token?.trim();
  if (t) return `${t} (Unresolved)`;
  return 'Unassigned';
}

function lineupDistributorCell(ln: CommercialLineupLine): string {
  if (ln.distributor_id != null) {
    const code = (ln.distributor_code ?? '').trim().toUpperCase();
    if (code === 'UNASSIGNED') return 'Distributor unassigned';
    const bits = [ln.distributor_code, ln.distributor_name].filter((x) => x?.trim());
    if (bits.length) return bits.join(' — ');
  }
  const t = (ln.distributor_token_raw ?? '').trim();
  if (t) return `${t} (Unresolved)`;
  return 'Unassigned';
}

function lineupIssuesCell(ln: CommercialLineupLine): string {
  const bits = [...(ln.diagnostic_codes || [])];
  if (ln.sync_skip_detail) bits.push(ln.sync_skip_detail);
  else if (ln.sync_skip_reason) bits.push(`sync preview: ${ln.sync_skip_reason}`);
  return bits.length ? bits.join(', ') : ln.row_status;
}

/** User-facing staging labels — internal enum values unchanged. */
function lineupCaseStatusLabel(status: string): string {
  const m: Record<string, string> = {
    draft_imported: 'Imported',
    validated: 'Reviewing',
    pending_review: 'Needs review',
    accepted: 'Ready to sync',
    synced: 'Synced to planner',
    po_pending: 'PO linked',
    po_issued: 'PO issued',
    work_closed: 'Work closed',
    cancelled: 'Cancelled',
    superseded: 'Superseded',
  };
  return m[status] ?? status;
}

// ── Status chip colors ─────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'> =
  {
    draft_imported: 'default',
    validated: 'info',
    pending_review: 'warning',
    accepted: 'success',
    synced: 'success',
    po_pending: 'secondary',
    po_issued: 'secondary',
    work_closed: 'default',
    in_fulfillment: 'info',
    received_closed: 'default',
    cancelled: 'error',
    superseded: 'default',
  };

// Staging-only transitions for current-lineup cases (not PO/customer workflow).
// Internal values map to staging labels via lineupCaseStatusLabel.
const ALLOWED_TRANSITIONS: Record<string, string[]> = {
  draft_imported: ['validated', 'cancelled'],
  validated: ['pending_review', 'cancelled'],
  pending_review: ['accepted', 'validated', 'cancelled'],
  accepted: ['cancelled'],
  synced: [],
  cancelled: [],
};

function buildCaseLinesSearchParams(opts: {
  commercialPlanId: number | null | undefined;
  fallbackCustomerId: string;
  fallbackDistributorId: string;
  defaultSrpLocal: string;
  allowZeroQuantity: boolean;
  workbenchScope: 'active' | 'synced' | 'ready' | 'blocked' | 'all';
}): string {
  const p = new URLSearchParams();
  p.set('include_product_specs', 'true');
  p.set('include_line_uploaded', 'true');
  if (!opts.commercialPlanId) return p.toString();
  p.set('include_sync_eligibility', 'true');
  p.set('workbench_scope', opts.workbenchScope);
  const fc = Number(opts.fallbackCustomerId.trim());
  if (Number.isFinite(fc) && fc > 0) p.set('fallback_customer_id', String(Math.trunc(fc)));
  const fd = Number(opts.fallbackDistributorId.trim());
  if (Number.isFinite(fd) && fd > 0) p.set('fallback_distributor_id', String(Math.trunc(fd)));
  const srp = Number(opts.defaultSrpLocal.trim());
  if (Number.isFinite(srp) && srp > 0) p.set('default_srp_local', String(srp));
  if (opts.allowZeroQuantity) p.set('allow_zero_quantity', 'true');
  return p.toString();
}

type CustomerTokenResolutionMode = 'map_customer' | 'customer_as_distributor' | 'open_channel' | 'create_customer';
type DistributorTokenResolutionMode = 'map_distributor' | 'distributor_as_customer' | 'create_distributor';

type EntityResolutionApplyItem = {
  kind: string;
  token: string;
  action?: string;
  dim_id?: number;
  new_code?: string;
  new_name?: string;
  confirm_create?: boolean;
};

function tokenAffectsCase(t: EntityTokenCandidate, caseId: number | null | undefined): boolean {
  if (!caseId) return true;
  const ids = t.case_ids ?? [];
  return ids.length === 0 || ids.includes(caseId);
}

function LineupEntityResolutionDialog({
  open,
  onClose,
  caseId,
  caseStatus,
  planScope,
  onApplied,
}: {
  open: boolean;
  onClose: () => void;
  onApplied: () => void;
  caseId?: number;
  caseStatus?: string;
  planScope?: {
    planId: number | null;
    caseIds: number[];
    filterCaseId?: number | null;
  };
}) {
  const isPlanScope = Boolean(planScope);
  const qc = useQueryClient();
  const [custModes, setCustModes] = useState<Record<string, CustomerTokenResolutionMode>>({});
  const [distModes, setDistModes] = useState<Record<string, DistributorTokenResolutionMode>>({});
  const [customerPicks, setCustomerPicks] = useState<Record<string, CustomerPick | null>>({});
  const [distributorPicks, setDistributorPicks] = useState<Record<string, DistributorPick | null>>({});
  const [distributorForCustToken, setDistributorForCustToken] = useState<Record<string, DistributorPick | null>>({});
  const [customerForDistToken, setCustomerForDistToken] = useState<Record<string, CustomerPick | null>>({});
  const [custCreate, setCustCreate] = useState<Record<string, { code: string; name: string; confirm: boolean }>>({});
  const [distCreate, setDistCreate] = useState<Record<string, { code: string; name: string; confirm: boolean }>>({});
  const [applyError, setApplyError] = useState<string | null>(null);

  const candidatesUrl = useMemo(() => {
    if (isPlanScope && planScope) {
      if (planScope.planId != null) {
        return `/api/v1/commercial-planner/entity-resolution-candidates?plan_id=${planScope.planId}`;
      }
      if (planScope.caseIds.length) {
        return `/api/v1/commercial-planner/entity-resolution-candidates?case_ids=${planScope.caseIds.join(',')}`;
      }
      return null;
    }
    if (caseId != null) {
      return `/api/v1/commercial-planner/lineup-cases/${caseId}/entity-resolution-candidates`;
    }
    return null;
  }, [isPlanScope, planScope, caseId]);

  const candidatesEnabled =
    open &&
    candidatesUrl != null &&
    (isPlanScope || (caseStatus != null && RESOLUTION_UI_STATUSES.has(caseStatus)));

  const { data: rawData, isLoading } = useQuery<EntityResolutionCandidatesResponse>({
    queryKey: ['lineup-entity-resolution-candidates', candidatesUrl, planScope?.filterCaseId ?? null],
    queryFn: ({ signal }) => apiGet<EntityResolutionCandidatesResponse>(candidatesUrl!, { signal }),
    enabled: candidatesEnabled,
  });

  const data = useMemo(() => {
    if (!rawData) return null;
    const filterId = planScope?.filterCaseId ?? null;
    if (!filterId) return rawData;
    return {
      ...rawData,
      customer_tokens: rawData.customer_tokens.filter((t) => tokenAffectsCase(t, filterId)),
      distributor_tokens: rawData.distributor_tokens.filter((t) => tokenAffectsCase(t, filterId)),
    };
  }, [rawData, planScope?.filterCaseId]);

  useEffect(() => {
    if (!open) {
      setCustModes({});
      setDistModes({});
      setCustomerPicks({});
      setDistributorPicks({});
      setDistributorForCustToken({});
      setCustomerForDistToken({});
      setCustCreate({});
      setDistCreate({});
      setApplyError(null);
      return;
    }
    if (!data) return;
    setCustModes(
      Object.fromEntries(data.customer_tokens.map((t) => [t.token_norm, 'map_customer' satisfies CustomerTokenResolutionMode])),
    );
    setDistModes(
      Object.fromEntries(
        data.distributor_tokens.map((t) => [t.token_norm, 'map_distributor' satisfies DistributorTokenResolutionMode]),
      ),
    );
    setCustomerPicks({});
    setDistributorPicks({});
    setDistributorForCustToken({});
    setCustomerForDistToken({});
    setCustCreate({});
    setDistCreate({});
    setApplyError(null);
  }, [open, caseId, planScope, data, isPlanScope]);

  const applyMutation = useMutation({
    mutationFn: async (resolutions: EntityResolutionApplyItem[]) => {
      if (isPlanScope && planScope) {
        await apiPost('/api/v1/commercial-planner/entity-resolutions/apply', {
          resolutions,
          plan_id: planScope.planId,
          case_ids: planScope.caseIds.length ? planScope.caseIds : undefined,
        });
        return;
      }
      await apiPost(`/api/v1/commercial-planner/lineup-cases/${caseId}/entity-resolutions/apply`, {
        resolutions,
      });
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['lineup-entity-resolution-candidates'] });
      await qc.invalidateQueries({ queryKey: ['lineup-plan-entity-resolution-candidates'] });
      if (caseId != null) {
        await qc.invalidateQueries({ queryKey: ['commercial-lineup-case-lines', caseId] });
        await qc.invalidateQueries({ queryKey: ['lineup-workbench-column-metadata', caseId] });
      }
      if (planScope?.caseIds.length) {
        await Promise.all(
          planScope.caseIds.map((id) => qc.invalidateQueries({ queryKey: ['commercial-lineup-case-lines', id] })),
        );
      }
      await qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
      await qc.invalidateQueries({ queryKey: ['sync-to-plan-preview'] });
      onApplied();
      onClose();
    },
    onError: (e: unknown) => {
      setApplyError(e instanceof Error ? e.message : 'Apply failed');
    },
  });

  const handleApply = () => {
    setApplyError(null);
    if (!data) return;
    const resolutions: EntityResolutionApplyItem[] = [];

    for (const t of data.customer_tokens) {
      const token = (t.token_display || t.token_norm).trim();
      if (!token) continue;
      const mode = custModes[t.token_norm] ?? 'map_customer';
      if (mode === 'open_channel') {
        resolutions.push({ kind: 'customer', token, action: 'mark_open_channel_staging' });
      } else if (mode === 'create_customer') {
        const c = custCreate[t.token_norm];
        const code = c?.code?.trim() ?? '';
        const name = c?.name?.trim() ?? '';
        if (code || name || c?.confirm) {
          if (!code || !name || !c?.confirm) {
            setApplyError('Create customer: enter code and name and tick confirmation, or clear those fields.');
            return;
          }
          resolutions.push({
            kind: 'customer',
            token,
            action: 'create_dim',
            new_code: code,
            new_name: name,
            confirm_create: true,
          });
        }
      } else if (mode === 'customer_as_distributor') {
        const pick = distributorForCustToken[t.token_norm];
        if (pick) {
          resolutions.push({
            kind: 'customer_token_as_distributor',
            token,
            action: 'map_existing',
            dim_id: pick.id,
          });
        }
      } else {
        const pick = customerPicks[t.token_norm];
        if (pick) {
          resolutions.push({ kind: 'customer', token, action: 'map_existing', dim_id: pick.id });
        }
      }
    }

    for (const t of data.distributor_tokens) {
      const token = (t.token_display || t.token_norm).trim();
      if (!token) continue;
      const mode = distModes[t.token_norm] ?? 'map_distributor';
      if (mode === 'create_distributor') {
        const c = distCreate[t.token_norm];
        const code = c?.code?.trim() ?? '';
        const name = c?.name?.trim() ?? '';
        if (code || name || c?.confirm) {
          if (!code || !name || !c?.confirm) {
            setApplyError('Create distributor: enter code and name and tick confirmation, or clear those fields.');
            return;
          }
          resolutions.push({
            kind: 'distributor',
            token,
            action: 'create_dim',
            new_code: code,
            new_name: name,
            confirm_create: true,
          });
        }
      } else if (mode === 'distributor_as_customer') {
        const pick = customerForDistToken[t.token_norm];
        if (pick) {
          resolutions.push({
            kind: 'distributor_token_as_customer',
            token,
            action: 'map_existing',
            dim_id: pick.id,
          });
        }
      } else {
        const pick = distributorPicks[t.token_norm];
        if (pick) {
          resolutions.push({ kind: 'distributor', token, action: 'map_existing', dim_id: pick.id });
        }
      }
    }

    if (!resolutions.length) {
      setApplyError('Select at least one completed resolution (map, redirect, Open Channel, or confirmed create).');
      return;
    }
    applyMutation.mutate(resolutions);
  };

  const totalUnresolved =
    (data?.customer_tokens.length ?? 0) + (data?.distributor_tokens.length ?? 0);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        {isPlanScope
          ? `Resolve lineup entities${planScope?.planId != null ? ` — plan #${planScope.planId}` : ''}`
          : 'Resolve lineup entities (this case only)'}
      </DialogTitle>
      <DialogContent dividers>
        <Alert severity="info" sx={{ mb: 2 }}>
          {isPlanScope ? (
            <>
              One mapping applies to every eligible case that shares the token (
              {rawData?.eligible_case_count ?? 0} case{(rawData?.eligible_case_count ?? 0) === 1 ? '' : 's'} in
              draft/review). Open Channel auto-detected rows are excluded from the customer list.
            </>
          ) : (
            <>
              Map file tokens with explicit actions only — abbreviations (for example IC, MITSUMI) are never auto-created
              or guessed. Raw tokens stay in the row audit trail. Lineup updates only — DAP stays evidence-only and is not
              used as cost.
            </>
          )}
        </Alert>
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
            <CircularProgress size={28} />
          </Box>
        ) : !data || totalUnresolved === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No unresolved customer or distributor tokens on this case.
          </Typography>
        ) : (
          <Stack spacing={3}>
            {data.customer_tokens.length > 0 && (
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Customer column tokens ({data.customer_tokens.length})
                </Typography>
                <Stack spacing={2.5}>
                  {data.customer_tokens.map((t) => {
                    const mode = custModes[t.token_norm] ?? 'map_customer';
                    const lid = `cust-res-${t.token_norm}`;
                    return (
                      <Box key={`c-${t.token_norm}`}>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Token ({t.line_count} row{t.line_count === 1 ? '' : 's'}
                          {t.case_count != null && t.case_count > 0
                            ? ` · ${t.case_count} case${t.case_count === 1 ? '' : 's'}`
                            : ''}
                          ): {t.token_display}
                        </Typography>
                        {t.case_ids && t.case_ids.length > 0 && (
                          <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                            {t.case_ids.map((cid) => (
                              <Chip key={cid} size="small" variant="outlined" label={`#${cid}`} />
                            ))}
                          </Stack>
                        )}
                        <FormControl fullWidth size="small" sx={{ mt: 1 }}>
                          <InputLabel id={`${lid}-mode`}>Resolution</InputLabel>
                          <Select
                            labelId={`${lid}-mode`}
                            label="Resolution"
                            value={mode}
                            onChange={(e) =>
                              setCustModes((prev) => ({
                                ...prev,
                                [t.token_norm]: e.target.value as CustomerTokenResolutionMode,
                              }))
                            }
                          >
                            <MenuItem value="map_customer">Map to existing customer</MenuItem>
                            <MenuItem value="customer_as_distributor">
                              Token is a distributor (channel stock / distributor column)
                            </MenuItem>
                            <MenuItem value="open_channel">Mark as Open Channel staging (end customer unassigned)</MenuItem>
                            <MenuItem value="create_customer">Create new customer (requires confirmation)</MenuItem>
                          </Select>
                          <FormHelperText>
                            Mis-filed tokens (for example a distributor name in the customer column) use the second
                            option — still explicit user action.
                          </FormHelperText>
                        </FormControl>
                        {mode === 'map_customer' && (
                          <EntitySearchAutocomplete<CustomerPick>
                            label="Map to customer"
                            helperText="Search master data; nothing is auto-created."
                            value={customerPicks[t.token_norm] ?? null}
                            onChange={(next) =>
                              setCustomerPicks((prev) => ({ ...prev, [t.token_norm]: next }))
                            }
                            fetchOptions={async (q, signal) => {
                              const res = await apiGet<{ items: CustomerPick[] }>(
                                `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                                { signal },
                              );
                              return res.items;
                            }}
                            getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
                          />
                        )}
                        {mode === 'customer_as_distributor' && (
                          <EntitySearchAutocomplete<DistributorPick>
                            label="Map token to distributor"
                            helperText="Search distributors; assigns distributor_id from the customer-column token."
                            value={distributorForCustToken[t.token_norm] ?? null}
                            onChange={(next) =>
                              setDistributorForCustToken((prev) => ({ ...prev, [t.token_norm]: next }))
                            }
                            fetchOptions={async (q, signal) => {
                              const res = await apiGet<{ items: DistributorPick[] }>(
                                `/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                                { signal },
                              );
                              return res.items;
                            }}
                            getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
                          />
                        )}
                        {mode === 'create_customer' && (
                          <Stack spacing={1} sx={{ mt: 1 }}>
                            <TextField
                              size="small"
                              label="New customer code"
                              value={custCreate[t.token_norm]?.code ?? ''}
                              onChange={(e) =>
                                setCustCreate((prev) => ({
                                  ...prev,
                                  [t.token_norm]: {
                                    code: e.target.value,
                                    name: prev[t.token_norm]?.name ?? '',
                                    confirm: prev[t.token_norm]?.confirm ?? false,
                                  },
                                }))
                              }
                            />
                            <TextField
                              size="small"
                              label="New customer name"
                              value={custCreate[t.token_norm]?.name ?? ''}
                              onChange={(e) =>
                                setCustCreate((prev) => ({
                                  ...prev,
                                  [t.token_norm]: {
                                    code: prev[t.token_norm]?.code ?? '',
                                    name: e.target.value,
                                    confirm: prev[t.token_norm]?.confirm ?? false,
                                  },
                                }))
                              }
                            />
                            <FormControlLabel
                              control={
                                <Checkbox
                                  size="small"
                                  checked={custCreate[t.token_norm]?.confirm ?? false}
                                  onChange={(e) =>
                                    setCustCreate((prev) => ({
                                      ...prev,
                                      [t.token_norm]: {
                                        code: prev[t.token_norm]?.code ?? '',
                                        name: prev[t.token_norm]?.name ?? '',
                                        confirm: e.target.checked,
                                      },
                                    }))
                                  }
                                />
                              }
                              label="I confirm creating this customer in master data"
                            />
                          </Stack>
                        )}
                      </Box>
                    );
                  })}
                </Stack>
              </Box>
            )}
            {data.distributor_tokens.length > 0 && (
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Distributor column tokens ({data.distributor_tokens.length})
                </Typography>
                <Stack spacing={2.5}>
                  {data.distributor_tokens.map((t) => {
                    const mode = distModes[t.token_norm] ?? 'map_distributor';
                    const lid = `dist-res-${t.token_norm}`;
                    return (
                      <Box key={`d-${t.token_norm}`}>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Token ({t.line_count} row{t.line_count === 1 ? '' : 's'}
                          {t.case_count != null && t.case_count > 0
                            ? ` · ${t.case_count} case${t.case_count === 1 ? '' : 's'}`
                            : ''}
                          ): {t.token_display}
                        </Typography>
                        {t.case_ids && t.case_ids.length > 0 && (
                          <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                            {t.case_ids.map((cid) => (
                              <Chip key={cid} size="small" variant="outlined" label={`#${cid}`} />
                            ))}
                          </Stack>
                        )}
                        {t.token_source === 'open_channel_route' && (
                          <Chip size="small" color="info" variant="outlined" label="Open Channel route" sx={{ mt: 0.5 }} />
                        )}
                        <FormControl fullWidth size="small" sx={{ mt: 1 }}>
                          <InputLabel id={`${lid}-mode`}>Resolution</InputLabel>
                          <Select
                            labelId={`${lid}-mode`}
                            label="Resolution"
                            value={mode}
                            onChange={(e) =>
                              setDistModes((prev) => ({
                                ...prev,
                                [t.token_norm]: e.target.value as DistributorTokenResolutionMode,
                              }))
                            }
                          >
                            <MenuItem value="map_distributor">Map to existing distributor</MenuItem>
                            <MenuItem value="distributor_as_customer">
                              Token is a customer (map into customer column)
                            </MenuItem>
                            <MenuItem value="create_distributor">Create new distributor (requires confirmation)</MenuItem>
                          </Select>
                        </FormControl>
                        {mode === 'map_distributor' && (
                          <EntitySearchAutocomplete<DistributorPick>
                            label="Map to distributor"
                            helperText="Search master data; nothing is auto-created."
                            value={distributorPicks[t.token_norm] ?? null}
                            onChange={(next) =>
                              setDistributorPicks((prev) => ({ ...prev, [t.token_norm]: next }))
                            }
                            fetchOptions={async (q, signal) => {
                              const res = await apiGet<{ items: DistributorPick[] }>(
                                `/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                                { signal },
                              );
                              return res.items;
                            }}
                            getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
                          />
                        )}
                        {mode === 'distributor_as_customer' && (
                          <EntitySearchAutocomplete<CustomerPick>
                            label="Map token to customer"
                            helperText="Search customers; assigns customer_id from the distributor-column token."
                            value={customerForDistToken[t.token_norm] ?? null}
                            onChange={(next) =>
                              setCustomerForDistToken((prev) => ({ ...prev, [t.token_norm]: next }))
                            }
                            fetchOptions={async (q, signal) => {
                              const res = await apiGet<{ items: CustomerPick[] }>(
                                `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                                { signal },
                              );
                              return res.items;
                            }}
                            getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
                          />
                        )}
                        {mode === 'create_distributor' && (
                          <Stack spacing={1} sx={{ mt: 1 }}>
                            <TextField
                              size="small"
                              label="New distributor code"
                              value={distCreate[t.token_norm]?.code ?? ''}
                              onChange={(e) =>
                                setDistCreate((prev) => ({
                                  ...prev,
                                  [t.token_norm]: {
                                    code: e.target.value,
                                    name: prev[t.token_norm]?.name ?? '',
                                    confirm: prev[t.token_norm]?.confirm ?? false,
                                  },
                                }))
                              }
                            />
                            <TextField
                              size="small"
                              label="New distributor name"
                              value={distCreate[t.token_norm]?.name ?? ''}
                              onChange={(e) =>
                                setDistCreate((prev) => ({
                                  ...prev,
                                  [t.token_norm]: {
                                    code: prev[t.token_norm]?.code ?? '',
                                    name: e.target.value,
                                    confirm: prev[t.token_norm]?.confirm ?? false,
                                  },
                                }))
                              }
                            />
                            <FormControlLabel
                              control={
                                <Checkbox
                                  size="small"
                                  checked={distCreate[t.token_norm]?.confirm ?? false}
                                  onChange={(e) =>
                                    setDistCreate((prev) => ({
                                      ...prev,
                                      [t.token_norm]: {
                                        code: prev[t.token_norm]?.code ?? '',
                                        name: prev[t.token_norm]?.name ?? '',
                                        confirm: e.target.checked,
                                      },
                                    }))
                                  }
                                />
                              }
                              label="I confirm creating this distributor in master data"
                            />
                          </Stack>
                        )}
                      </Box>
                    );
                  })}
                </Stack>
              </Box>
            )}
            {applyError && <Alert severity="error">{applyError}</Alert>}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose}>
          Close
        </Button>
        <Button
          size="small"
          variant="contained"
          disabled={applyMutation.isPending || isLoading || !data || totalUnresolved === 0}
          onClick={handleApply}
          data-testid="lineup-entity-resolution-apply"
        >
          {applyMutation.isPending ? 'Applying…' : 'Apply resolutions'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Types: sync ───────────────────────────────────────────────────────────────

type SyncPreview = {
  case_id: number;
  plan_id: number;
  total_lines: number;
  will_create: number;
  skipped_duplicates: number;
  skipped_unresolved: number;
  skipped_unresolved_product: number;
  skipped_missing_customer: number;
  skipped_open_channel_account_missing?: number;
  skipped_missing_distributor: number;
  skipped_missing_quantity: number;
  skipped_missing_srp: number;
};

type SyncResult = {
  case_id: number;
  plan_id: number;
  created: number;
  skipped_duplicates: number;
  skipped_unresolved: number;
  skipped_unresolved_product: number;
  skipped_missing_customer: number;
  skipped_open_channel_account_missing?: number;
  skipped_missing_distributor: number;
  skipped_missing_quantity: number;
  skipped_missing_srp: number;
  failed: number;
  created_line_ids: number[];
  warnings: string[];
};

// ── Sub-components ────────────────────────────────────────────────────────────

function SyncPreviewDialog({
  open,
  onClose,
  caseItem,
  onSyncComplete,
}: {
  open: boolean;
  onClose: () => void;
  caseItem: CommercialLineupCase;
  onSyncComplete?: (info: { planId: number; caseId: number }) => void;
}) {
  const qc = useQueryClient();
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [fallbackCustomerId, setFallbackCustomerId] = useState('');
  const [fallbackDistributorId, setFallbackDistributorId] = useState('');
  const [defaultSrpLocal, setDefaultSrpLocal] = useState('');
  const [allowZeroQuantity, setAllowZeroQuantity] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSyncResult(null);
    setSyncError(null);
  }, [open, caseItem.id]);

  const previewQuerySuffix = useMemo(() => {
    const p = new URLSearchParams();
    if (caseItem.commercial_plan_id != null) {
      p.set('commercial_plan_id', String(caseItem.commercial_plan_id));
    }
    const fc = Number(fallbackCustomerId.trim());
    if (Number.isFinite(fc) && fc > 0) p.set('fallback_customer_id', String(Math.trunc(fc)));
    const fd = Number(fallbackDistributorId.trim());
    if (Number.isFinite(fd) && fd > 0) p.set('fallback_distributor_id', String(Math.trunc(fd)));
    const srp = Number(defaultSrpLocal.trim());
    if (Number.isFinite(srp) && srp > 0) p.set('default_srp_local', String(srp));
    if (allowZeroQuantity) p.set('allow_zero_quantity', 'true');
    const s = p.toString();
    return s ? `?${s}` : '';
  }, [
    caseItem.commercial_plan_id,
    fallbackCustomerId,
    fallbackDistributorId,
    defaultSrpLocal,
    allowZeroQuantity,
  ]);

  const previewUrl = `/api/v1/commercial-planner/lineup-cases/${caseItem.id}/sync-to-plan/preview${previewQuerySuffix}`;

  const syncBody = useMemo(
    () => ({
      commercial_plan_id: caseItem.commercial_plan_id ?? null,
      fallback_customer_id:
        Number.isFinite(Number(fallbackCustomerId.trim())) && Number(fallbackCustomerId.trim()) > 0
          ? Math.trunc(Number(fallbackCustomerId.trim()))
          : null,
      fallback_distributor_id:
        Number.isFinite(Number(fallbackDistributorId.trim())) && Number(fallbackDistributorId.trim()) > 0
          ? Math.trunc(Number(fallbackDistributorId.trim()))
          : null,
      default_srp_local:
        Number.isFinite(Number(defaultSrpLocal.trim())) && Number(defaultSrpLocal.trim()) > 0
          ? Number(defaultSrpLocal.trim())
          : null,
      allow_zero_quantity: allowZeroQuantity,
    }),
    [
      caseItem.commercial_plan_id,
      fallbackCustomerId,
      fallbackDistributorId,
      defaultSrpLocal,
      allowZeroQuantity,
    ],
  );

  const { data: preview, isLoading: previewLoading } = useQuery<SyncPreview>({
    queryKey: ['sync-to-plan-preview', caseItem.id, previewQuerySuffix],
    queryFn: ({ signal }) => apiGet<SyncPreview>(previewUrl, { signal }),
    enabled: open && !syncResult,
  });

  const syncMutation = useMutation({
    mutationFn: () =>
      apiPost<SyncResult>(
        `/api/v1/commercial-planner/lineup-cases/${caseItem.id}/sync-to-plan`,
        syncBody,
      ),
    onSuccess: (result) => {
      setSyncResult(result);
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-case-lines', caseItem.id] });
      void qc.invalidateQueries({ queryKey: ['lineup-workbench-column-metadata', caseItem.id] });
      void qc.invalidateQueries({ queryKey: ['sync-to-plan-preview'] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-lines', result.plan_id] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-summary', result.plan_id] });
      void qc.invalidateQueries({ queryKey: ['commercial-column-metadata', result.plan_id] });
      void qc.invalidateQueries({ queryKey: ['commercial-plans'] });
      void qc.invalidateQueries({ queryKey: ['plan-readiness', result.plan_id] });
      onSyncComplete?.({ planId: result.plan_id, caseId: result.case_id });
    },
    onError: (e: unknown) => {
      setSyncError(e instanceof Error ? e.message : 'Sync failed');
    },
  });

  const handleClose = () => {
    setSyncResult(null);
    setSyncError(null);
    setFallbackCustomerId('');
    setFallbackDistributorId('');
    setDefaultSrpLocal('');
    setAllowZeroQuantity(false);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Sync to plan</DialogTitle>
      <DialogContent>
        {syncResult ? (
          <Alert severity="success">
            <Typography variant="body2">
              Sync complete: <strong>{syncResult.created}</strong> line
              {syncResult.created !== 1 ? 's' : ''} created.
            </Typography>
            {syncResult.skipped_duplicates > 0 && (
              <Typography variant="body2">
                Skipped {syncResult.skipped_duplicates} duplicate(s).
              </Typography>
            )}
            {syncResult.skipped_unresolved_product != null && syncResult.skipped_unresolved_product > 0 && (
              <Typography variant="body2">
                Skipped — unresolved product: {syncResult.skipped_unresolved_product}
              </Typography>
            )}
            {syncResult.skipped_missing_customer != null && syncResult.skipped_missing_customer > 0 && (
              <Typography variant="body2">
                Skipped — missing customer (use fallback or fix file): {syncResult.skipped_missing_customer}
              </Typography>
            )}
            {syncResult.skipped_open_channel_account_missing != null &&
              syncResult.skipped_open_channel_account_missing > 0 && (
                <Typography variant="body2">
                  Blocked — reference data missing: controlled dim_customer OPEN_CHANNEL not found (not a normal row
                  mapping issue). From repo root run pnpm local:db:seed or pnpm docker:seed — never create from upload
                  tokens: {syncResult.skipped_open_channel_account_missing}
                </Typography>
              )}
            {syncResult.skipped_missing_distributor != null && syncResult.skipped_missing_distributor > 0 && (
              <Typography variant="body2">
                Skipped — distributor required for sync (includes unresolved distributor_token rows and missing
                UNASSIGNED placeholder when distributor was intentionally blank). Map a distributor, use fallback, or
                seed dim_distributor UNASSIGNED: {syncResult.skipped_missing_distributor}
              </Typography>
            )}
            {syncResult.skipped_missing_quantity != null && syncResult.skipped_missing_quantity > 0 && (
              <Typography variant="body2">
                Skipped — missing quantity: {syncResult.skipped_missing_quantity}
              </Typography>
            )}
            {syncResult.skipped_unresolved > 0 && (
              <Typography variant="body2" color="text.secondary">
                Total blocked rows (excl. duplicates / missing SRP): {syncResult.skipped_unresolved}
              </Typography>
            )}
            {syncResult.skipped_missing_srp > 0 && (
              <Typography variant="body2">
                Skipped {syncResult.skipped_missing_srp} missing SRP.
              </Typography>
            )}
            {syncResult.warnings.length > 0 && (
              <Typography variant="body2">
                Warnings: {syncResult.warnings.join('; ')}
              </Typography>
            )}
          </Alert>
        ) : syncError ? (
          <Alert severity="error">{syncError}</Alert>
        ) : (
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              Optional fallbacks apply to preview and to the sync request. They do not change DAP evidence on lineup
              rows.
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <TextField
                size="small"
                label="Fallback customer id"
                value={fallbackCustomerId}
                onChange={(e) => setFallbackCustomerId(e.target.value)}
                sx={{ width: 168 }}
              />
              <TextField
                size="small"
                label="Fallback distributor id"
                value={fallbackDistributorId}
                onChange={(e) => setFallbackDistributorId(e.target.value)}
                sx={{ width: 176 }}
              />
              <TextField
                size="small"
                label="Default SRP (local)"
                value={defaultSrpLocal}
                onChange={(e) => setDefaultSrpLocal(e.target.value)}
                sx={{ width: 140 }}
              />
            </Stack>
            <FormControlLabel
              control={
                <Checkbox
                  size="small"
                  checked={allowZeroQuantity}
                  onChange={(e) => setAllowZeroQuantity(e.target.checked)}
                />
              }
              label="Allow missing quantity (treat as 0 for sync)"
            />
            <Divider />
            {previewLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
                <CircularProgress size={28} />
              </Box>
            ) : preview ? (
              <Stack spacing={1.5}>
                <Typography variant="body2">
                  Total lines in this lineup case: <strong>{preview.total_lines}</strong>
                </Typography>
                <Typography variant="body2" color="success.main">
                  Eligible planner lines (would be created): <strong>{preview.will_create}</strong>
                </Typography>
                {preview.skipped_duplicates > 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Skipped — already in plan: {preview.skipped_duplicates}
                  </Typography>
                )}
                {preview.skipped_unresolved_product != null && preview.skipped_unresolved_product > 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Skipped — unresolved product: {preview.skipped_unresolved_product}
                  </Typography>
                )}
                {preview.skipped_missing_customer != null && preview.skipped_missing_customer > 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Skipped — missing customer: {preview.skipped_missing_customer}
                  </Typography>
                )}
                {preview.skipped_open_channel_account_missing != null &&
                  preview.skipped_open_channel_account_missing > 0 && (
                    <Typography variant="body2" color="error">
                      Blocked — reference data setup: dim_customer OPEN_CHANNEL missing (pnpm local:db:seed or pnpm
                      docker:seed). Not a row-mapping issue — do not create from file tokens:{' '}
                      {preview.skipped_open_channel_account_missing}
                    </Typography>
                  )}
                {preview.skipped_missing_distributor != null && preview.skipped_missing_distributor > 0 && (
                  <Typography variant="body2" color="error">
                    Blocked — distributor required for planner lines (unresolved distributor tokens, or intentionally
                    blank distributor without UNASSIGNED seed). Map distributor, use fallback, or seed UNASSIGNED:{' '}
                    {preview.skipped_missing_distributor}
                  </Typography>
                )}
                {preview.skipped_missing_quantity != null && preview.skipped_missing_quantity > 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Skipped — missing quantity: {preview.skipped_missing_quantity}
                  </Typography>
                )}
                {preview.skipped_unresolved > 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Total blocked (excl. duplicates / missing SRP): {preview.skipped_unresolved}
                  </Typography>
                )}
                {preview.skipped_missing_srp > 0 && (
                  <Typography variant="body2" color="text.secondary">
                    Skipped — missing SRP: {preview.skipped_missing_srp}
                  </Typography>
                )}
              </Stack>
            ) : null}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={handleClose}>
          {syncResult ? 'Close' : 'Cancel'}
        </Button>
        {!syncResult && (
          <Button
            size="small"
            variant="contained"
            disabled={syncMutation.isPending || previewLoading || !preview}
            onClick={() => syncMutation.mutate()}
            data-testid="sync-to-plan-confirm"
          >
            {syncMutation.isPending ? 'Syncing…' : 'Sync to plan'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

function CaseLinesDialog({
  open,
  onClose,
  caseId,
  caseLabel,
}: {
  open: boolean;
  onClose: () => void;
  caseId: number;
  caseLabel: string;
}) {
  const { data, isLoading } = useQuery<CaseLinesResponse>({
    queryKey: ['commercial-lineup-case-lines', caseId],
    queryFn: ({ signal }) =>
      apiGet<CaseLinesResponse>(`/api/v1/commercial-planner/lineup-cases/${caseId}/lines`, { signal }),
    enabled: open,
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg" aria-labelledby="case-lines-title">
      <DialogTitle id="case-lines-title">Lines — {caseLabel}</DialogTitle>
      <DialogContent dividers>
        {data?.dap_semantics_note && (
          <Alert severity="info" sx={{ mb: 2 }}>
            {data.dap_semantics_note}
          </Alert>
        )}
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress size={32} />
          </Box>
        ) : !data?.lines?.length ? (
          <Typography color="text.secondary">No lines in this case.</Typography>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>Model / product</TableCell>
                  <TableCell>SKU</TableCell>
                  <TableCell>Part #</TableCell>
                  <TableCell>Customer</TableCell>
                  <TableCell>Distributor</TableCell>
                  <TableCell>Units</TableCell>
                  <TableCell>MSRP local</TableCell>
                  <TableCell>Promo evidence</TableCell>
                  <TableCell>DAP evidence</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.lines.map((ln) => (
                  <TableRow key={ln.id}>
                    <TableCell>{ln.source_row_number ?? ln.id}</TableCell>
                    <TableCell>
                      <Typography variant="body2">{lineupProductLabel(ln)}</Typography>
                      {ln.product_sku && ln.sku_raw && ln.product_sku !== ln.sku_raw && (
                        <Typography variant="caption" color="text.secondary" display="block">
                          SKU raw: {ln.sku_raw}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {ln.product_sku ?? ln.sku_raw ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell>{ln.product_part_number ?? ln.part_number_raw ?? '—'}</TableCell>
                    <TableCell>{lineupCustomerCell(ln)}</TableCell>
                    <TableCell>{lineupDistributorCell(ln)}</TableCell>
                    <TableCell>{ln.quantity_units != null ? ln.quantity_units.toLocaleString() : '—'}</TableCell>
                    <TableCell>{ln.msrp_local != null ? ln.msrp_local.toLocaleString() : '—'}</TableCell>
                    <TableCell>
                      {ln.promo_price_evidence_local != null ? ln.promo_price_evidence_local.toLocaleString() : '—'}
                    </TableCell>
                    <TableCell>
                      {ln.dap_evidence_local != null ? ln.dap_evidence_local.toLocaleString() : '—'}
                    </TableCell>
                    <TableCell>
                      <Chip label={ln.row_status} size="small" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function StatusTransitionDialog({
  open,
  onClose,
  currentCase,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  currentCase: CommercialLineupCase;
  onConfirm: (status: string, notes: string, acceptedBy?: string) => void;
}) {
  const allowed = ALLOWED_TRANSITIONS[currentCase.commercial_status] ?? [];
  const [nextStatus, setNextStatus] = useState(allowed[0] ?? '');
  const [notes, setNotes] = useState('');
  const [markedBy, setMarkedBy] = useState('');

  const confirmLabel =
    nextStatus === 'accepted' ? 'Mark ready to sync' : nextStatus === 'cancelled' ? 'Cancel case' : 'Update status';

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Update staging status</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Current status: <strong>{lineupCaseStatusLabel(currentCase.commercial_status)}</strong>
          </Typography>
          {allowed.length === 0 ? (
            <Alert severity="info">This case is in a terminal state and cannot be transitioned further.</Alert>
          ) : (
            <FormControl size="small" fullWidth>
              <InputLabel>New status</InputLabel>
              <Select
                value={nextStatus}
                label="New status"
                onChange={(e) => setNextStatus(e.target.value)}
              >
                {allowed.map((s) => (
                  <MenuItem key={s} value={s}>
                    {lineupCaseStatusLabel(s)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          {nextStatus === 'accepted' && (
            <TextField
              size="small"
              label="Marked ready by (optional)"
              value={markedBy}
              onChange={(e) => setMarkedBy(e.target.value)}
              fullWidth
            />
          )}
          <TextField
            size="small"
            label="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            multiline
            rows={2}
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          disabled={!nextStatus || allowed.length === 0}
          onClick={() => {
            onConfirm(nextStatus, notes, markedBy || undefined);
            onClose();
          }}
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Reconciliation inline summary (Session C Unit 3) ──────────────────────────

type ReconProduct = {
  product_id: number;
  product_name: string | null;
  units_flag: string;
  customer_id?: number | null;
};

type ReconResponse = {
  case_id: number;
  linked_po_count: number;
  products: ReconProduct[];
  customers?: ReconCustomerSlice[];
  po_flags: { purchase_order_id: number; po_number_raw: string | null; flag: string }[];
  summary: ReconSummary;
  data_unavailable?: boolean;
};

function CaseReconciliationInline({ caseId }: { caseId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['lineup-po-reconciliation', caseId],
    queryFn: ({ signal }) =>
      apiGet<ReconResponse>(`/api/v1/commercial-planner/lineup/po-reconciliation?case_id=${caseId}`, { signal }),
  });

  if (isLoading) {
    return (
      <Typography variant="caption" color="text.secondary">
        Loading reconciliation…
      </Typography>
    );
  }
  if (!data || data.data_unavailable) {
    return (
      <Typography variant="caption" color="text.secondary">
        Reconciliation unavailable.
      </Typography>
    );
  }

  const summary = data.summary ?? {};

  return (
    <Stack spacing={0.5} data-testid={`recon-inline-${caseId}`}>
      <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="caption" color="text.secondary" fontWeight={600}>
          Reconciliation:
        </Typography>
        <ReconSummaryChips summary={summary} />
        <Button
          size="small"
          variant="text"
          component={NextLink}
          href={`/admin/po-management`}
          data-testid={`recon-drill-${caseId}`}
        >
          View PO management
        </Button>
      </Stack>
      {data.customers?.length ? (
        <CustomerReconChips customers={data.customers} testIdPrefix={`recon-inline-customers-${caseId}`} />
      ) : null}
    </Stack>
  );
}

// ── Confirm lineup with PO(s) (Session C Unit 2d) ─────────────────────────────

function AssignDistributorDialog({
  open,
  onClose,
  currentCase,
  isPending,
  error,
  onAssign,
}: {
  open: boolean;
  onClose: () => void;
  currentCase: CommercialLineupCase;
  isPending: boolean;
  error: string | null;
  onAssign: (payload: {
    distributor_id?: number;
    new_code?: string;
    new_name?: string;
    confirm_create?: boolean;
  }) => void;
}) {
  const [chosen, setChosen] = useState<DistributorPick | null>(null);
  const [createMode, setCreateMode] = useState(false);
  const [newCode, setNewCode] = useState('');
  const [newName, setNewName] = useState('');
  const [confirmCreate, setConfirmCreate] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['lineup-suggested-distributors', currentCase.id],
    queryFn: ({ signal }) =>
      apiGet<SuggestedDistributorsResponse>(
        `/api/v1/commercial-planner/lineup-cases/${currentCase.id}/suggested-distributors`,
        { signal },
      ),
    enabled: open,
  });

  useEffect(() => {
    if (!open) return;
    setChosen(null);
    setCreateMode(false);
    setNewCode('');
    setNewName('');
    setConfirmCreate(false);
  }, [open, currentCase.id]);

  const suggestions = data?.suggested_distributors ?? [];
  const converged = data?.converged ?? false;

  const canCreate =
    createMode && newCode.trim().length > 0 && newName.trim().length > 0 && confirmCreate;
  const canAssign = !isPending && (canCreate || (!createMode && chosen != null));

  const handleAssign = () => {
    if (canCreate) {
      onAssign({ new_code: newCode.trim(), new_name: newName.trim(), confirm_create: true });
    } else if (chosen) {
      onAssign({ distributor_id: chosen.id });
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Assign distributor</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Assigns a distributor to this case&apos;s lines that do not yet have one. Suggestions come
            from shipment evidence (products in this lineup that were shipped under a distributor&apos;s
            POs) and are always existing distributor records. If the right distributor is not listed,
            search for it or create a new one.
          </Typography>

          {isLoading && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CircularProgress size={18} />
              <Typography variant="body2" color="text.secondary">
                Loading shipment-evidence suggestions…
              </Typography>
            </Box>
          )}

          {!isLoading && converged && suggestions[0] && (
            <Alert severity="success" data-testid="assign-dist-converged">
              Shipment evidence points to a single distributor:{' '}
              <strong>{suggestions[0].distributor_name ?? suggestions[0].distributor_code}</strong> (
              {suggestions[0].matched_product_count} matched product
              {suggestions[0].matched_product_count === 1 ? '' : 's'}).
            </Alert>
          )}
          {!isLoading && !converged && suggestions.length > 1 && (
            <Alert severity="info" data-testid="assign-dist-ambiguous">
              Shipment evidence is ambiguous — these products were shipped under{' '}
              {data?.distinct_count} different distributors. Pick the correct one, or search / create.
            </Alert>
          )}
          {!isLoading && suggestions.length === 0 && (
            <Alert severity="info" data-testid="assign-dist-none">
              No distributor could be suggested from shipment evidence for this case. Search for a
              distributor or create a new one.
            </Alert>
          )}

          {suggestions.length > 0 && !createMode && (
            <Box data-testid="assign-dist-suggestions">
              <Typography variant="subtitle2" gutterBottom>
                Suggested from shipment evidence
              </Typography>
              <Stack spacing={1}>
                {suggestions.map((s) => (
                  <Button
                    key={s.distributor_id}
                    fullWidth
                    variant={chosen?.id === s.distributor_id ? 'contained' : 'outlined'}
                    onClick={() =>
                      setChosen({
                        id: s.distributor_id,
                        distributor_code: s.distributor_code ?? '',
                        distributor_name: s.distributor_name ?? '',
                      })
                    }
                    sx={{ justifyContent: 'space-between', textTransform: 'none' }}
                    data-testid={`assign-dist-suggestion-${s.distributor_id}`}
                  >
                    <span>
                      {s.distributor_name ?? s.distributor_code}
                      {s.already_assigned ? ' (already on some lines)' : ''}
                    </span>
                    <span>
                      {s.matched_product_count} product{s.matched_product_count === 1 ? '' : 's'} ·{' '}
                      {s.po_count} PO{s.po_count === 1 ? '' : 's'}
                    </span>
                  </Button>
                ))}
              </Stack>
            </Box>
          )}

          {!createMode && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Or search all distributors
              </Typography>
              <EntitySearchAutocomplete<DistributorPick>
                label="Search distributors"
                value={chosen}
                onChange={(next) => setChosen(next)}
                fetchOptions={async (q) => {
                  const res = await apiGet<{ items: DistributorPick[] }>(
                    `/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                  );
                  return res.items;
                }}
                getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
              />
            </Box>
          )}

          <Divider />
          <FormControlLabel
            control={
              <Checkbox
                checked={createMode}
                onChange={(e) => {
                  setCreateMode(e.target.checked);
                  setChosen(null);
                }}
                data-testid="assign-dist-create-toggle"
              />
            }
            label="Create a new distributor instead"
          />
          {createMode && (
            <Stack spacing={2}>
              <TextField
                label="New distributor code"
                value={newCode}
                onChange={(e) => setNewCode(e.target.value)}
                size="small"
                inputProps={{ maxLength: 32 }}
                data-testid="assign-dist-new-code"
              />
              <TextField
                label="New distributor name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                size="small"
                inputProps={{ maxLength: 256 }}
                data-testid="assign-dist-new-name"
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={confirmCreate}
                    onChange={(e) => setConfirmCreate(e.target.checked)}
                    data-testid="assign-dist-confirm-create"
                  />
                }
                label="I confirm creating this distributor in master data"
              />
            </Stack>
          )}

          {error && (
            <Alert severity="error" data-testid="assign-dist-error">
              {error}
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={isPending}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleAssign}
          disabled={!canAssign}
          data-testid="assign-dist-submit"
        >
          {isPending ? 'Assigning…' : 'Assign distributor'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}


function ConfirmWithPoDialog({
  open,
  onClose,
  currentCase,
  isPending,
  error,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  currentCase: CommercialLineupCase;
  isPending: boolean;
  error: string | null;
  onConfirm: (poNumbers: string[], notes: string) => void;
}) {
  const [pos, setPos] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [notes, setNotes] = useState('');
  const [selectedNorms, setSelectedNorms] = useState<Set<string>>(new Set());

  const { data: suggestedData, isLoading: suggestionsLoading } = useQuery({
    queryKey: ['lineup-suggested-pos', currentCase.id],
    queryFn: ({ signal }) =>
      apiGet<{ case_id: number; suggestions: SuggestedPo[] }>(
        `/api/v1/commercial-planner/lineup-cases/${currentCase.id}/suggested-pos`,
        { signal },
      ),
    enabled: open,
  });

  useEffect(() => {
    if (!open) return;
    setPos([]);
    setInput('');
    setNotes('');
    setSelectedNorms(new Set());
  }, [open, currentCase.id]);

  const suggestions = suggestedData?.suggestions ?? [];

  const addTokens = (raw: string) => {
    const tokens = raw
      .split(/[\n,;\t]+/)
      .map((t) => t.trim())
      .filter(Boolean);
    if (!tokens.length) return;
    setPos((prev) => {
      const seen = new Set(prev.map((p) => p.toUpperCase()));
      const merged = [...prev];
      for (const t of tokens) {
        if (!seen.has(t.toUpperCase())) {
          seen.add(t.toUpperCase());
          merged.push(t);
        }
      }
      return merged;
    });
    setInput('');
  };

  const removePo = (idx: number) => setPos((prev) => prev.filter((_, i) => i !== idx));

  const toggleSuggestion = (s: SuggestedPo) => {
    if (s.already_linked) return;
    setSelectedNorms((prev) => {
      const next = new Set(prev);
      if (next.has(s.po_number_norm)) next.delete(s.po_number_norm);
      else next.add(s.po_number_norm);
      return next;
    });
  };

  const collectPoNumbers = (): string[] => {
    const fromSuggestions = suggestions
      .filter((s) => selectedNorms.has(s.po_number_norm))
      .map((s) => s.po_number);
    const all = [...fromSuggestions, ...pos];
    const trailing = input.trim();
    if (trailing) all.push(trailing);
    const seen = new Set<string>();
    const out: string[] = [];
    for (const p of all) {
      const key = p.toUpperCase();
      if (!seen.has(key)) {
        seen.add(key);
        out.push(p);
      }
    }
    return out;
  };

  const alreadyLinked = currentCase.linked_pos ?? [];
  const hasLinked = (currentCase.po_count ?? 0) > 0 || alreadyLinked.length > 0;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{hasLinked ? 'Add purchase order(s)' : 'Confirm with PO'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Links one or more PO numbers to this case and sets status to <strong>PO issued</strong>.
            No review-step ladder required — use this for historical lineups already fulfilled.
            Re-adding an existing PO is a no-op; new POs append.
          </Typography>

          {alreadyLinked.length > 0 && (
            <Box>
              <Typography variant="caption" color="text.secondary">
                Already linked:
              </Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                {alreadyLinked.map((p) => (
                  <Chip key={p.purchase_order_id} size="small" variant="outlined" label={p.po_number_raw} />
                ))}
              </Stack>
            </Box>
          )}

          {suggestionsLoading && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CircularProgress size={18} />
              <Typography variant="body2" color="text.secondary">
                Loading observed PO suggestions…
              </Typography>
            </Box>
          )}

          {!suggestionsLoading && suggestions.length > 0 && (
            <Box data-testid="confirm-po-suggestions">
              <Typography variant="subtitle2" gutterBottom>
                Suggested from shipment evidence
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox" />
                    <TableCell>PO number</TableCell>
                    <TableCell>Distributor</TableCell>
                    <TableCell align="right">Products matched</TableCell>
                    <TableCell align="right">Shipped units</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {suggestions.map((s) => (
                    <TableRow
                      key={s.purchase_order_id}
                      hover={!s.already_linked}
                      sx={{ opacity: s.already_linked ? 0.6 : 1 }}
                    >
                      <TableCell padding="checkbox">
                        <Checkbox
                          size="small"
                          checked={s.already_linked || selectedNorms.has(s.po_number_norm)}
                          disabled={s.already_linked || isPending}
                          onChange={() => toggleSuggestion(s)}
                          inputProps={{
                            'aria-label': `Include PO ${s.po_number}`,
                          }}
                        />
                      </TableCell>
                      <TableCell>
                        {s.po_number}
                        {s.already_linked && (
                          <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                            (linked)
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        {[s.distributor_code, s.distributor_name].filter(Boolean).join(' — ') || '—'}
                      </TableCell>
                      <TableCell align="right">{s.matched_product_count}</TableCell>
                      <TableCell align="right">{s.total_shipped_units.toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          )}

          {!suggestionsLoading && suggestions.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              No observed POs match this case&apos;s distributor and products. Enter a PO number manually below.
            </Typography>
          )}

          <TextField
            size="small"
            label="PO number(s) — manual entry"
            placeholder="e.g. PO-12345"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                addTokens(input);
              }
            }}
            onBlur={() => addTokens(input)}
            fullWidth
            data-testid="confirm-po-input"
          />

          {pos.length > 0 && (
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap data-testid="confirm-po-chips">
              {pos.map((p, idx) => (
                <Chip key={`${p}:${idx}`} size="small" color="primary" label={p} onDelete={() => removePo(idx)} />
              ))}
            </Stack>
          )}

          <TextField
            size="small"
            label="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            multiline
            rows={2}
            fullWidth
          />

          {error && (
            <Alert severity="error" data-testid="confirm-po-error">
              {error}
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose} disabled={isPending}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          disabled={isPending || collectPoNumbers().length === 0}
          onClick={() => {
            const all = collectPoNumbers();
            if (!all.length) return;
            onConfirm(all, notes);
          }}
          data-testid="confirm-po-submit"
        >
          {isPending ? 'Confirming…' : 'Confirm'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Retry parse on empty draft case ───────────────────────────────────────────

function RetryParseDialog({
  open,
  onClose,
  targetCase,
  onParsed,
}: {
  open: boolean;
  onClose: () => void;
  targetCase: CommercialLineupCase;
  onParsed: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{
    total_rows: number;
    resolved_products: number;
    unresolved_products: number;
    warnings: string[];
  } | null>(null);

  const handleClose = () => {
    setFile(null);
    setError(null);
    setPreview(null);
    onClose();
  };

  const handlePreview = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    setPreview(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(
        `/api/v1/commercial-planner/lineup-cases/${targetCase.id}/parse-preview`,
        { method: 'POST', body: fd },
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        setError(`Preview failed. ${formatHttpErrorDetail(errBody.detail)}`);
        return;
      }
      const data = await res.json();
      setPreview({
        total_rows: data.total_rows,
        resolved_products: data.resolved_products,
        unresolved_products: data.unresolved_products,
        warnings: data.warnings ?? [],
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Preview failed');
    } finally {
      setUploading(false);
    }
  };

  const handleApply = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('confirm', 'true');
      const parseRes = await fetch(
        `/api/v1/commercial-planner/lineup-cases/${targetCase.id}/parse-apply`,
        { method: 'POST', body: fd },
      );
      if (parseRes.status === 202) {
        setError(null);
        onParsed();
        handleClose();
        return;
      }
      if (!parseRes.ok) {
        const errBody = await parseRes.json().catch(() => ({}));
        setError(
          `Apply failed. ${formatHttpErrorDetail(errBody.detail)} You can fix the file and try again.`,
        );
        return;
      }
      onParsed();
      handleClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Upload file — case #{targetCase.id}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            This case has no lines yet. Choose a lineup file (.csv, .xlsx, .xlsm) to parse into the case.
          </Typography>
          <Button variant="outlined" component="label" size="small">
            {file ? file.name : 'Choose file…'}
            <input
              type="file"
              hidden
              accept=".csv,.xlsx,.xlsm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </Button>
          {preview ? (
            <Alert severity="info" data-testid="lineup-parse-preview-summary">
              Preview: {preview.total_rows} rows — {preview.resolved_products} products resolved,{' '}
              {preview.unresolved_products} unresolved.
              {preview.warnings.length > 0 ? ` Warnings: ${preview.warnings.join('; ')}` : ''}
            </Alert>
          ) : null}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={handleClose}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="outlined"
          onClick={() => void handlePreview()}
          disabled={!file || uploading}
          data-testid="retry-parse-preview"
        >
          {uploading && !preview ? 'Previewing…' : 'Preview'}
        </Button>
        <Button
          size="small"
          variant="contained"
          onClick={() => void handleApply()}
          disabled={!file || !preview || uploading}
          data-testid="retry-parse-confirm"
        >
          {uploading && preview ? 'Applying…' : 'Apply to case'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Upload / create case dialog ────────────────────────────────────────────────

function UploadLineupDialog({
  open,
  onClose,
  activePlanId,
  planCountryCode,
  planCurrencyCode,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  activePlanId: number | null;
  planCountryCode?: string | null;
  planCurrencyCode?: string | null;
  onCreated: () => void;
}) {
  const [periodLabel, setPeriodLabel] = useState('');
  const [currencyCode, setCurrencyCode] = useState('ZAR');
  const [countryCode, setCountryCode] = useState('ZA');
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdCaseId, setCreatedCaseId] = useState<number | null>(null);
  const [preview, setPreview] = useState<{
    total_rows: number;
    resolved_products: number;
    unresolved_products: number;
    warnings: string[];
    can_apply: boolean;
  } | null>(null);

  useEffect(() => {
    if (!open) return;
    const cc = (planCountryCode ?? '').trim() || 'ZA';
    const cur = (planCurrencyCode ?? '').trim() || 'USD';
    setCountryCode(cc.length <= 3 ? cc.toUpperCase() : 'ZA');
    setCurrencyCode(cur.length >= 3 ? cur.toUpperCase().slice(0, 8) : 'USD');
  }, [open, planCountryCode, planCurrencyCode]);

  const handleClose = () => {
    setFile(null);
    setError(null);
    setPeriodLabel('');
    setNotes('');
    setCreatedCaseId(null);
    setPreview(null);
    onClose();
  };

  const handleCreateCase = async () => {
    if (!activePlanId) return;
    setCreating(true);
    setError(null);
    setPreview(null);
    try {
      const caseResponse = await apiPost<{ id: number }>('/api/v1/commercial-planner/lineup-cases', {
        commercial_plan_id: activePlanId,
        period_label: periodLabel.trim() || null,
        currency_code: currencyCode,
        country_code: countryCode,
        notes: notes.trim() || null,
      });
      setCreatedCaseId(caseResponse.id);
      if (!file) {
        onCreated();
        handleClose();
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to create lineup case';
      setError(msg);
    } finally {
      setCreating(false);
    }
  };

  const handlePreviewFile = async () => {
    if (!file || createdCaseId == null) return;
    setCreating(true);
    setError(null);
    setPreview(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(
        `/api/v1/commercial-planner/lineup-cases/${createdCaseId}/parse-preview`,
        { method: 'POST', body: fd },
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        setError(`Preview failed. ${formatHttpErrorDetail(errBody.detail)}`);
        return;
      }
      const data = await res.json();
      setPreview({
        total_rows: data.total_rows,
        resolved_products: data.resolved_products,
        unresolved_products: data.unresolved_products,
        warnings: data.warnings ?? [],
        can_apply: Boolean(data.can_apply),
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Preview failed');
    } finally {
      setCreating(false);
    }
  };

  const handleApplyFile = async () => {
    if (!file || createdCaseId == null) return;
    setCreating(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('confirm', 'true');
      const parseRes = await fetch(
        `/api/v1/commercial-planner/lineup-cases/${createdCaseId}/parse-apply`,
        { method: 'POST', body: fd },
      );
      if (parseRes.status === 202) {
        onCreated();
        handleClose();
        return;
      }
      if (!parseRes.ok) {
        const errBody = await parseRes.json().catch(() => ({}));
        setError(
          `Case created (id=${createdCaseId}) but apply failed. ` +
            `Use "Upload file to this case" on the case card to retry. ` +
            formatHttpErrorDetail(errBody.detail),
        );
        return;
      }
      onCreated();
      handleClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Apply failed');
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Upload current lineup</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            size="small"
            label="Period label"
            value={periodLabel}
            onChange={(e) => setPeriodLabel(e.target.value)}
            placeholder="e.g. Q2 2026"
            fullWidth
          />
          <Typography variant="caption" color="text.secondary" display="block">
            Country and currency describe this uploaded lineup (metadata only; no FX conversion here).
          </Typography>
          <Stack direction="row" spacing={2}>
            <FormControl size="small" sx={{ flex: 1 }} data-testid="upload-lineup-country">
              <InputLabel id="upload-lineup-country-label">Country</InputLabel>
              <Select
                labelId="upload-lineup-country-label"
                label="Country"
                value={countryCode}
                onChange={(e) => setCountryCode(String(e.target.value))}
              >
                <MenuItem value="ZA">ZA</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ flex: 1 }} data-testid="upload-lineup-currency">
              <InputLabel id="upload-lineup-currency-label">Currency</InputLabel>
              <Select
                labelId="upload-lineup-currency-label"
                label="Currency"
                value={currencyCode}
                onChange={(e) => setCurrencyCode(String(e.target.value))}
              >
                <MenuItem value="ZAR">ZAR</MenuItem>
                <MenuItem value="USD">USD</MenuItem>
              </Select>
            </FormControl>
          </Stack>
          <TextField
            size="small"
            label="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            multiline
            rows={2}
            fullWidth
          />
          <Box>
            <Typography variant="caption" color="text.secondary" gutterBottom display="block">
              Lineup file (optional — can be uploaded after case creation)
            </Typography>
            <Button variant="outlined" component="label" size="small">
              {file ? file.name : 'Choose file…'}
              <input
                type="file"
                hidden
                accept=".csv,.xlsx,.xlsm"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Button>
          </Box>
          {createdCaseId != null && file ? (
            <Alert severity="success">Case #{createdCaseId} created. Preview the file before apply.</Alert>
          ) : null}
          {preview ? (
            <Alert severity="info" data-testid="upload-lineup-parse-preview-summary">
              Preview: {preview.total_rows} rows — {preview.resolved_products} products resolved,{' '}
              {preview.unresolved_products} unresolved.
              {!preview.can_apply ? ' Nothing resolvable to apply.' : ''}
              {preview.warnings.length > 0 ? ` Warnings: ${preview.warnings.join('; ')}` : ''}
            </Alert>
          ) : null}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={handleClose}>
          Cancel
        </Button>
        {createdCaseId != null && file ? (
          <>
            <Button
              size="small"
              variant="outlined"
              onClick={() => void handlePreviewFile()}
              disabled={creating}
              data-testid="upload-lineup-preview"
            >
              {creating && !preview ? 'Previewing…' : 'Preview file'}
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={() => void handleApplyFile()}
              disabled={creating || !preview?.can_apply}
              data-testid="upload-lineup-apply"
            >
              {creating && preview ? 'Applying…' : 'Apply to case'}
            </Button>
          </>
        ) : (
          <Button
            size="small"
            variant="contained"
            onClick={() => void handleCreateCase()}
            disabled={creating}
            data-testid="upload-lineup-confirm"
          >
            {creating ? 'Creating…' : 'Create'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

function LineupLineNumericEditor({
  disabled,
  initial,
  onCommit,
  width,
}: {
  disabled?: boolean;
  initial: number | null;
  onCommit: (next: number | null) => void;
  width: number;
}) {
  const [text, setText] = useState(initial != null ? String(initial) : '');
  useEffect(() => {
    setText(initial != null ? String(initial) : '');
  }, [initial]);
  return (
    <TextField
      size="small"
      type="number"
      disabled={disabled}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        const t = text.trim();
        if (t === '') {
          onCommit(null);
          return;
        }
        const n = Number(t);
        if (!Number.isFinite(n)) return;
        onCommit(n);
      }}
      sx={{ width }}
    />
  );
}

// ── Main section ──────────────────────────────────────────────────────────────

export function CurrentLineupSection({
  activePlanId,
  planLineCount = 0,
  planCountryCode,
  planCurrencyCode,
  onSyncComplete,
  onStagedLineupSummary,
  allowUpload = false,
}: {
  activePlanId: number | null;
  planLineCount?: number;
  planCountryCode?: string | null;
  planCurrencyCode?: string | null;
  onSyncComplete?: (info: { planId: number; caseId: number }) => void;
  onStagedLineupSummary?: (summary: { caseId: number | null; lineCount: number }) => void;
  /**
   * When false (default), the embedded lineup upload is read-only: the section points users to the
   * unified importer in the Import Centre instead. The legacy in-section upload dialogs are retained
   * behind this flag so existing flows/tests can still opt in.
   */
  allowUpload?: boolean;
}) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [viewLinesCase, setViewLinesCase] = useState<CommercialLineupCase | null>(null);
  const [statusCase, setStatusCase] = useState<CommercialLineupCase | null>(null);
  const [syncCase, setSyncCase] = useState<CommercialLineupCase | null>(null);
  const [confirmCase, setConfirmCase] = useState<CommercialLineupCase | null>(null);
  const [assignDistCase, setAssignDistCase] = useState<CommercialLineupCase | null>(null);
  const [retryParseCase, setRetryParseCase] = useState<CommercialLineupCase | null>(null);
  const [deleteCase, setDeleteCase] = useState<CommercialLineupCase | null>(null);
  const [activeCaseId, setActiveCaseId] = useState<number | null>(null);
  const [resolutionCase, setResolutionCase] = useState<CommercialLineupCase | null>(null);
  const [planResolutionOpen, setPlanResolutionOpen] = useState(false);
  const [planResolutionFilterCaseId, setPlanResolutionFilterCaseId] = useState<number | null>(null);
  const [wbSync, setWbSync] = useState({
    fallbackCustomerId: '',
    fallbackDistributorId: '',
    defaultSrpLocal: '',
    allowZeroQuantity: false,
  });
  const [workbenchScope, setWorkbenchScope] = useState<'active' | 'synced' | 'ready' | 'blocked' | 'all'>('active');
  const [colSelectorOpen, setColSelectorOpen] = useState(false);
  const [colSelectorSearch, setColSelectorSearch] = useState('');

  // Plan-optional browse: a lineup case is viewable on its own. When a plan is selected we filter to
  // it by default, but the user can toggle "Show all" to see every case (linked or unlinked). When no
  // plan exists at all, we always list everything.
  const [showAllCases, setShowAllCases] = useState(false);
  const [showWorkClosed, setShowWorkClosed] = useState(false);
  const effectivePlanId = showAllCases ? null : activePlanId;

  const lineupCasesQueryKey = [
    'commercial-lineup-cases',
    effectivePlanId,
    showWorkClosed ? 'with-closed' : 'active',
  ] as const;

  const { data: cases, isLoading } = useQuery<CommercialLineupCase[]>({
    queryKey: lineupCasesQueryKey,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      if (effectivePlanId != null) params.set('plan_id', String(effectivePlanId));
      if (showWorkClosed) params.set('include_work_closed', 'true');
      const qs = params.toString();
      return apiGet<CommercialLineupCase[]>(
        `/api/v1/commercial-planner/lineup-cases${qs ? `?${qs}` : ''}`,
        { signal },
      );
    },
  });

  useEffect(() => {
    if (!cases?.length) {
      setActiveCaseId(null);
      return;
    }
    setActiveCaseId((prev) => {
      if (prev != null && cases.some((c) => c.id === prev)) return prev;
      const preferred = cases.find((c) => c.line_count > 0) ?? cases[0];
      return preferred?.id ?? null;
    });
  }, [cases]);

  const activeCase = cases?.find((c) => c.id === activeCaseId);

  const eligibleResolutionCaseIds = useMemo(
    () => (cases ?? []).filter((c) => RESOLUTION_UI_STATUSES.has(c.commercial_status)).map((c) => c.id),
    [cases],
  );

  const planEntityCandidatesEnabled =
    eligibleResolutionCaseIds.length > 0 &&
    (effectivePlanId != null || !showAllCases || (cases?.length ?? 0) > 0);

  const { data: planEntitySummary } = useQuery<EntityResolutionCandidatesResponse>({
    queryKey: [
      'lineup-plan-entity-resolution-candidates',
      effectivePlanId,
      eligibleResolutionCaseIds.join(','),
    ],
    queryFn: ({ signal }) => {
      const url =
        effectivePlanId != null
          ? `/api/v1/commercial-planner/entity-resolution-candidates?plan_id=${effectivePlanId}`
          : `/api/v1/commercial-planner/entity-resolution-candidates?case_ids=${eligibleResolutionCaseIds.join(',')}`;
      return apiGet<EntityResolutionCandidatesResponse>(url, { signal });
    },
    enabled: planEntityCandidatesEnabled && eligibleResolutionCaseIds.length > 0,
  });

  const unresolvedTokenCountByCase = useMemo(() => {
    const map = new Map<number, number>();
    const customerTokens = planEntitySummary?.customer_tokens;
    const distributorTokens = planEntitySummary?.distributor_tokens;
    // Guards: mocks / partial payloads may not be a full EntityResolutionCandidatesResponse.
    if (!Array.isArray(customerTokens) || !Array.isArray(distributorTokens)) return map;
    const bumpToken = (caseIds: number[] | undefined) => {
      for (const id of caseIds ?? []) {
        map.set(id, (map.get(id) ?? 0) + 1);
      }
    };
    for (const t of customerTokens) bumpToken(t.case_ids);
    for (const t of distributorTokens) bumpToken(t.case_ids);
    return map;
  }, [planEntitySummary]);

  const hasWorkbenchPlan = Boolean(activeCase?.commercial_plan_id);

  const { data: wbMeta, isSuccess: wbMetaReady } = useQuery<WorkbenchColumnMetadata>({
    queryKey: ['lineup-workbench-column-metadata', activeCaseId],
    queryFn: ({ signal }) =>
      apiGet<WorkbenchColumnMetadata>(
        `/api/v1/commercial-planner/lineup-cases/${activeCaseId}/workbench-column-metadata`,
        { signal },
      ),
    // Case-scoped metadata; load it whenever a case is active, with or without a plan.
    enabled: activeCaseId != null,
  });

  const allowedWorkbenchIds = useMemo(
    () => mergeWorkbenchAllowedIds(wbMeta, hasWorkbenchPlan),
    [wbMeta, hasWorkbenchPlan],
  );

  const [visibleCols, setVisibleCols] = useState<string[]>([]);

  useEffect(() => {
    if (activeCaseId == null) {
      setVisibleCols([]);
      return;
    }
    if (!wbMetaReady) return;
    const allow = mergeWorkbenchAllowedIds(wbMeta, hasWorkbenchPlan);
    const defaults = defaultUnifiedLineupWorkbenchIds(wbMeta, hasWorkbenchPlan);
    const stored = readInitialWorkbenchVisible(activeCaseId, wbMeta, hasWorkbenchPlan);
    const chosen = stored.filter((id) => allow.has(id));
    setVisibleCols(chosen.length ? chosen : defaults.filter((id) => allow.has(id)));
  }, [activeCaseId, wbMetaReady, wbMeta, hasWorkbenchPlan]);

  useEffect(() => {
    if (activeCaseId == null || !visibleCols.length) return;
    saveCaseWorkbenchStorage(activeCaseId, visibleCols);
  }, [activeCaseId, visibleCols]);

  const columnMenuEntries = useMemo(() => {
    const rows: Array<{ kind: 'header'; label: string } | { kind: 'col'; id: string }> = [];
    const push = (label: string, ids: string[]) => {
      if (!ids.length) return;
      rows.push({ kind: 'header', label });
      for (const id of ids) rows.push({ kind: 'col', id });
    };
    push(
      'Core',
      CORE_WORKBENCH_IDS.filter((id) => id !== 'sync' || hasWorkbenchPlan),
    );
    if (wbMeta?.raw_columns?.length)
      push(
        'Raw upload (original column names)',
        wbMeta.raw_columns.map((c) => `raw:${c}`),
      );
    if (wbMeta?.parsed_fields?.length) push('Parsed staging fields', wbMeta.parsed_fields.map((p) => p.id));
    if (wbMeta?.calc_fields?.length)
      push('Calculated pricing chain', wbMeta.calc_fields.map((f) => f.id));
    if (wbMeta?.catalogue_product_fields?.length)
      push(
        'Matched catalogue / product fields',
        wbMeta.catalogue_product_fields.map((p) => p.id),
      );
    if (wbMeta?.catalogue_spec_keys?.length)
      push('Resolved product specs (specs_json keys)', wbMeta.catalogue_spec_keys.map((k) => `spec:${k}`));
    if (wbMeta?.sync_fields?.length && hasWorkbenchPlan) push('Sync diagnostics', wbMeta.sync_fields.map((f) => f.id));
    return rows;
  }, [wbMeta, hasWorkbenchPlan]);

  const caseLinesSuffix = useMemo(
    () =>
      buildCaseLinesSearchParams({
        commercialPlanId: activeCase?.commercial_plan_id ?? null,
        fallbackCustomerId: wbSync.fallbackCustomerId,
        fallbackDistributorId: wbSync.fallbackDistributorId,
        defaultSrpLocal: wbSync.defaultSrpLocal,
        allowZeroQuantity: wbSync.allowZeroQuantity,
        workbenchScope,
      }),
    [
      activeCase?.commercial_plan_id,
      wbSync.fallbackCustomerId,
      wbSync.fallbackDistributorId,
      wbSync.defaultSrpLocal,
      wbSync.allowZeroQuantity,
      workbenchScope,
    ],
  );

  const workingLinesUrl = useMemo(() => {
    if (activeCaseId == null) return null;
    const base = `/api/v1/commercial-planner/lineup-cases/${activeCaseId}/lines`;
    if (!caseLinesSuffix) return base;
    return `${base}?${caseLinesSuffix}`;
  }, [activeCaseId, caseLinesSuffix]);

  const { data: workingLinesData } = useQuery<CaseLinesResponse>({
    queryKey: ['commercial-lineup-case-lines', activeCaseId, caseLinesSuffix],
    queryFn: ({ signal }) => apiGet<CaseLinesResponse>(workingLinesUrl!, { signal }),
    // Plan-optional: the lines endpoint is case-scoped, so the workbench grid opens even for a
    // case not yet attached to a plan. Plan-specific extras (sync, sync diagnostics) stay gated on
    // activeCase.commercial_plan_id below.
    enabled: activeCaseId != null && workingLinesUrl != null,
  });

  const workingLines = useMemo(() => workingLinesData?.lines ?? [], [workingLinesData?.lines]);
  const workbenchCounts = workingLinesData?.workbench_counts;

  const showSyncWorkbenchCol = useMemo(
    () =>
      Boolean(activeCase?.commercial_plan_id) &&
      workingLines.length > 0 &&
      typeof workingLines[0]?.sync_eligible === 'boolean',
    [activeCase?.commercial_plan_id, workingLines],
  );

  useEffect(() => {
    const n = workbenchCounts?.all_lines ?? workingLines.length;
    onStagedLineupSummary?.({ caseId: activeCaseId, lineCount: n });
  }, [activeCaseId, workingLines.length, workbenchCounts?.all_lines, onStagedLineupSummary]);

  const patchLineMutation = useMutation({
    mutationFn: async (payload: {
      caseId: number;
      lineId: number;
      body: { quantity_units?: number | null; msrp_local?: number | null; promo_price_evidence_local?: number | null };
    }) => {
      await apiPatch(
        `/api/v1/commercial-planner/lineup-cases/${payload.caseId}/lines/${payload.lineId}`,
        payload.body
      );
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['commercial-lineup-case-lines', activeCaseId] });
      await qc.invalidateQueries({ queryKey: ['lineup-workbench-column-metadata', activeCaseId] });
      await qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
    },
  });

  const visibleColsFiltered = useMemo(
    () => visibleCols.filter((id) => allowedWorkbenchIds.has(id)),
    [visibleCols, allowedWorkbenchIds],
  );

  const wbCellContent = useCallback(
    (ln: CommercialLineupLine, colId: string, canEdit: boolean): ReactNode => {
      if (colId === 'num') return ln.source_row_number ?? ln.id;
      if (colId === 'product')
        return <Typography variant="body2">{lineupProductLabel(ln)}</Typography>;
      if (colId === 'sku')
        return (
          <Typography variant="body2" fontFamily="monospace">
            {ln.product_sku ?? ln.sku_raw ?? '—'}
          </Typography>
        );
      if (colId === 'part') return ln.product_part_number ?? ln.part_number_raw ?? '—';
      if (colId === 'cust') return lineupCustomerCell(ln);
      if (colId === 'dist') return lineupDistributorCell(ln);
      if (colId === 'units')
        return (
          <LineupLineNumericEditor
            disabled={!canEdit || patchLineMutation.isPending}
            initial={ln.quantity_units}
            width={88}
            onCommit={(next) => {
              if (!canEdit || next == null || !activeCaseId) return;
              if (next === ln.quantity_units) return;
              patchLineMutation.mutate({
                caseId: activeCaseId,
                lineId: ln.id,
                body: { quantity_units: next },
              });
            }}
          />
        );
      if (colId === 'msrp')
        return (
          <LineupLineNumericEditor
            disabled={!canEdit || patchLineMutation.isPending}
            initial={ln.msrp_local}
            width={100}
            onCommit={(next) => {
              if (!canEdit || next == null || !activeCaseId) return;
              if (next === ln.msrp_local) return;
              patchLineMutation.mutate({
                caseId: activeCaseId,
                lineId: ln.id,
                body: { msrp_local: next },
              });
            }}
          />
        );
      if (colId === 'promo')
        return (
          <LineupLineNumericEditor
            disabled={!canEdit || patchLineMutation.isPending}
            initial={ln.promo_price_evidence_local}
            width={100}
            onCommit={(next) => {
              if (!canEdit || next == null || !activeCaseId) return;
              if (next === ln.promo_price_evidence_local) return;
              patchLineMutation.mutate({
                caseId: activeCaseId,
                lineId: ln.id,
                body: { promo_price_evidence_local: next },
              });
            }}
          />
        );
      if (colId === 'dap')
        return ln.dap_evidence_local != null
          ? formatMoneyWorkbenchValue(ln.dap_evidence_local)
          : '—';
      if (colId.startsWith('calc:')) {
        const key = colId.slice(5);
        if (key === 'dap') {
          const v = ln.calc_dap_cost_currency ?? calcChainOutput(ln, 'calc_dap_cost_currency');
          return formatMoneyWorkbenchValue(v);
        }
        if (key === 'profit') {
          const v = ln.calc_profit_total ?? calcChainOutput(ln, 'calc_profit_total');
          return formatMoneyWorkbenchValue(v);
        }
        const outputKey =
          key === 'dealer_price'
            ? 'calc_dealer_price_local'
            : key === 'net_price'
              ? 'calc_net_price_local'
              : key === 'disti_cost'
                ? 'calc_disti_cost_local'
                : null;
        if (outputKey) return formatMoneyWorkbenchValue(calcChainOutput(ln, outputKey));
        return '—';
      }
      if (colId === 'issues')
        return <Typography variant="caption">{lineupIssuesCell(ln)}</Typography>;
      if (colId === 'sync') {
        return showSyncWorkbenchCol ? (
          <Stack spacing={0.5}>
            <Chip
              size="small"
              label={ln.sync_eligible ? 'eligible' : 'skipped'}
              color={
                ln.sync_eligible
                  ? ln.sync_ui_severity === 'warning'
                    ? 'warning'
                    : 'success'
                  : ln.sync_ui_severity === 'warning'
                    ? 'warning'
                    : 'default'
              }
              variant={ln.sync_eligible && ln.sync_ui_severity !== 'warning' ? 'filled' : 'outlined'}
            />
            {(ln.sync_skip_detail || (!ln.sync_eligible && ln.sync_skip_reason)) && (
              <Typography variant="caption" color="text.secondary">
                {ln.sync_skip_detail ?? ln.sync_skip_reason}
              </Typography>
            )}
          </Stack>
        ) : (
          <Typography variant="caption" color="text.secondary">
            —
          </Typography>
        );
      }
      if (colId.startsWith('raw:')) {
        const key = colId.slice(4);
        const up =
          ln.uploaded && typeof ln.uploaded === 'object' && !Array.isArray(ln.uploaded)
            ? (ln.uploaded as Record<string, unknown>)[key]
            : undefined;
        if (up == null || (typeof up === 'string' && !up.trim())) return '—';
        return String(up);
      }
      if (colId.startsWith('parsed:')) {
        const field = colId.slice(7);
        return formatParsedFieldForWorkbench(ln, field);
      }
      if (colId.startsWith('cat:')) {
        const field = colId.slice(4);
        return formatParsedFieldForWorkbench(ln, field);
      }
      if (colId.startsWith('spec:')) {
        const k = colId.slice(5);
        // Use product_specs_flat (flattened, non-empty map) — same keys as workbench-column-metadata
        // catalogue_spec_keys. This handles nested import_staging keys correctly.
        const flat = ln.product_specs_flat;
        if (!flat) return '—';
        const direct = flat[k];
        if (direct?.trim()) return direct;
        // Case-insensitive fallback for key casing mismatches
        const lower = k.toLowerCase();
        const matchKey = Object.keys(flat).find((fk) => fk.toLowerCase() === lower);
        const fallback = matchKey ? flat[matchKey] : undefined;
        return fallback?.trim() ? fallback : '—';
      }
      if (colId.startsWith('sync:')) {
        const field = colId.slice(5);
        return formatSyncFieldForWorkbench(ln, field);
      }
      return '—';
    },
    [activeCaseId, patchLineMutation, showSyncWorkbenchCol],
  );

  // Primitive value for AG Grid sort/filter (cellRenderer below handles rich display). Mirrors the
  // value branches of wbCellContent so sorting matches what the user sees.
  const wbCellValue = useCallback(
    (ln: CommercialLineupLine, colId: string): string | number | null => {
      if (colId === 'num') return ln.source_row_number ?? ln.id;
      if (colId === 'product') return lineupProductLabel(ln);
      if (colId === 'sku') return ln.product_sku ?? ln.sku_raw ?? '—';
      if (colId === 'part') return ln.product_part_number ?? ln.part_number_raw ?? '—';
      if (colId === 'cust') return lineupCustomerCell(ln);
      if (colId === 'dist') return lineupDistributorCell(ln);
      if (colId === 'units') return ln.quantity_units ?? null;
      if (colId === 'msrp') return ln.msrp_local ?? null;
      if (colId === 'promo') return ln.promo_price_evidence_local ?? null;
      if (colId === 'dap') return ln.dap_evidence_local ?? null;
      if (colId.startsWith('calc:')) {
        const key = colId.slice(5);
        if (key === 'dap') return ln.calc_dap_cost_currency ?? calcChainOutput(ln, 'calc_dap_cost_currency');
        if (key === 'profit') return ln.calc_profit_total ?? calcChainOutput(ln, 'calc_profit_total');
        const outputKey =
          key === 'dealer_price'
            ? 'calc_dealer_price_local'
            : key === 'net_price'
              ? 'calc_net_price_local'
              : key === 'disti_cost'
                ? 'calc_disti_cost_local'
                : null;
        return outputKey ? calcChainOutput(ln, outputKey) : null;
      }
      if (colId === 'issues') return lineupIssuesCell(ln);
      if (colId === 'sync') return showSyncWorkbenchCol ? (ln.sync_eligible ? 'eligible' : 'skipped') : '—';
      if (colId.startsWith('raw:')) {
        const key = colId.slice(4);
        const up =
          ln.uploaded && typeof ln.uploaded === 'object' && !Array.isArray(ln.uploaded)
            ? (ln.uploaded as Record<string, unknown>)[key]
            : undefined;
        if (up == null || (typeof up === 'string' && !up.trim())) return '—';
        return String(up);
      }
      if (colId.startsWith('parsed:')) return formatParsedFieldForWorkbench(ln, colId.slice(7));
      if (colId.startsWith('cat:')) return formatParsedFieldForWorkbench(ln, colId.slice(4));
      if (colId.startsWith('spec:')) {
        const k = colId.slice(5);
        const flat = ln.product_specs_flat;
        if (!flat) return '—';
        const direct = flat[k];
        if (direct?.trim()) return direct;
        const lower = k.toLowerCase();
        const matchKey = Object.keys(flat).find((fk) => fk.toLowerCase() === lower);
        const fallback = matchKey ? flat[matchKey] : undefined;
        return fallback?.trim() ? fallback : '—';
      }
      if (colId.startsWith('sync:')) return formatSyncFieldForWorkbench(ln, colId.slice(5));
      return '—';
    },
    [showSyncWorkbenchCol],
  );

  const wbCanEdit = activeCase?.commercial_status === 'draft_imported';

  const wbColumnDefs = useMemo<ColDef[]>(() => {
    return visibleColsFiltered.map((colId) => {
      const headerName = workbenchColumnLabel(colId, wbMeta);
      const editableField =
        colId === 'units'
          ? 'quantity_units'
          : colId === 'msrp'
            ? 'msrp_local'
            : colId === 'promo'
              ? 'promo_price_evidence_local'
              : null;
      if (wbCanEdit && editableField) {
        return {
          colId,
          headerName,
          editable: true,
          type: 'numericColumn',
          minWidth: 100,
          valueGetter: (p) =>
            p.data ? ((p.data as Record<string, unknown>)[editableField] as number | null) ?? null : null,
          valueFormatter: (p) => (p.value == null || p.value === '' ? '' : String(p.value)),
        } satisfies ColDef;
      }
      return {
        colId,
        headerName,
        minWidth: colId === 'num' ? 72 : 120,
        valueGetter: (p) => (p.data ? wbCellValue(p.data as CommercialLineupLine, colId) : null),
        cellRenderer: (p: ICellRendererParams<CommercialLineupLine>) =>
          p.data ? wbCellContent(p.data, colId, false) : null,
      } satisfies ColDef;
    });
  }, [visibleColsFiltered, wbMeta, wbCanEdit, wbCellValue, wbCellContent]);

  const onWbCellValueChanged = useCallback(
    (e: CellValueChangedEvent) => {
      if (!activeCaseId || !e.data) return;
      const colId = e.column.getColId();
      const field =
        colId === 'units'
          ? 'quantity_units'
          : colId === 'msrp'
            ? 'msrp_local'
            : colId === 'promo'
              ? 'promo_price_evidence_local'
              : null;
      if (!field) return;
      const raw = e.newValue;
      const next = raw == null || raw === '' ? null : Number(raw);
      // Mirror the prior inline editor: ignore null/invalid commits and no-ops.
      if (next == null || !Number.isFinite(next)) return;
      const current = (e.data as Record<string, unknown>)[field] as number | null;
      if (next === current) return;
      patchLineMutation.mutate({ caseId: activeCaseId, lineId: (e.data as CommercialLineupLine).id, body: { [field]: next } });
    },
    [activeCaseId, patchLineMutation],
  );

  const wbGridOptions = useMemo<GridOptions>(
    () => ({
      singleClickEdit: true,
      enableBrowserTooltips: true,
      onCellValueChanged: (e) => onWbCellValueChanged(e),
      // Persist user column reordering back into visibleCols (which is saved to localStorage).
      onDragStopped: (e) => {
        const order = e.api.getAllDisplayedColumns().map((c) => c.getColId());
        if (!order.length) return;
        setVisibleCols((prev) => {
          const displayed = new Set(order);
          const rest = prev.filter((id) => !displayed.has(id));
          const nextOrder = [...order, ...rest];
          if (nextOrder.length === prev.length && nextOrder.every((id, i) => id === prev[i])) {
            return prev;
          }
          return nextOrder;
        });
      },
    }),
    [onWbCellValueChanged],
  );

  const statusMutation = useMutation({
    mutationFn: ({
      caseId,
      status,
      notes,
      acceptedBy,
    }: {
      caseId: number;
      status: string;
      notes: string;
      acceptedBy?: string;
    }) =>
      apiPatch(`/api/v1/commercial-planner/lineup-cases/${caseId}/status`, {
        status,
        notes: notes || null,
        accepted_by: acceptedBy ?? null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (caseId: number) =>
      apiDelete(`/api/v1/commercial-planner/lineup-cases/${caseId}`),
    onSuccess: () => {
      setDeleteCase(null);
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
    },
  });

  const deletePreviewQ = useQuery({
    queryKey: ['lineup-case-delete-preview', deleteCase?.id],
    enabled: deleteCase != null,
    queryFn: ({ signal }) =>
      apiGet<{
        superseded_child_count: number;
        superseded_children: { id: number; file_name: string | null }[];
        message: string | null;
      }>(`/api/v1/commercial-planner/lineup-cases/${deleteCase!.id}/delete-preview`, { signal }),
  });

  const attachPlanMutation = useMutation({
    mutationFn: ({ caseId, planId }: { caseId: number; planId: number | null }) =>
      apiPatch(`/api/v1/commercial-planner/lineup-cases/${caseId}/plan`, {
        commercial_plan_id: planId,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] }),
  });

  const closeWorkMutation = useMutation({
    mutationFn: (caseId: number) =>
      apiPost(`/api/v1/commercial-planner/lineup-cases/${caseId}/close-work`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
    },
  });

  const confirmMutation = useMutation({
    mutationFn: ({ caseId, poNumbers, notes }: { caseId: number; poNumbers: string[]; notes: string }) =>
      apiPost(`/api/v1/commercial-planner/lineup-cases/${caseId}/confirm-with-po`, {
        po_numbers: poNumbers,
        notes: notes || null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
      void qc.invalidateQueries({ queryKey: ['po-reconciliation'] });
      setConfirmCase(null);
    },
  });

  const assignDistributorMutation = useMutation({
    mutationFn: ({
      caseId,
      payload,
    }: {
      caseId: number;
      payload: { distributor_id?: number; new_code?: string; new_name?: string; confirm_create?: boolean };
    }) =>
      apiPost(`/api/v1/commercial-planner/lineup-cases/${caseId}/assign-distributor`, payload),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
      void qc.invalidateQueries({ queryKey: ['commercial-lineup-case-lines', vars.caseId] });
      void qc.invalidateQueries({ queryKey: ['lineup-suggested-distributors', vars.caseId] });
      void qc.invalidateQueries({ queryKey: ['lineup-suggested-pos', vars.caseId] });
      setAssignDistCase(null);
    },
  });

  const count = cases?.length ?? 0;

  const caseFileNameById = useMemo(() => {
    const m = new Map<number, string>();
    for (const c of cases ?? []) {
      m.set(c.id, c.file_name ?? `(case #${c.id})`);
    }
    return m;
  }, [cases]);

  // Group for browse: period (period_label, falling back to inferred_period_start month) then
  // product_line. Derived only — no stored active flag. Newest period first.
  const groupedCases = useMemo(() => {
    const list = cases ?? [];
    const groups = new Map<
      string,
      { periodLabel: string; productLine: string; cases: CommercialLineupCase[] }
    >();
    for (const c of list) {
      const periodLabel =
        c.period_label ?? (c.inferred_period_start ? c.inferred_period_start.slice(0, 7) : 'No period');
      const productLine = c.product_line ?? 'Unclassified';
      const key = `${periodLabel}\u0000${productLine}`;
      let g = groups.get(key);
      if (!g) {
        g = { periodLabel, productLine, cases: [] };
        groups.set(key, g);
      }
      g.cases.push(c);
    }
    return Array.from(groups.values()).sort((a, b) =>
      a.periodLabel !== b.periodLabel
        ? b.periodLabel.localeCompare(a.periodLabel)
        : a.productLine.localeCompare(b.productLine),
    );
  }, [cases]);

  return (
    <>
      <Box sx={{ mb: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Button
            size="small"
            variant="text"
            onClick={() => setExpanded((e) => !e)}
            endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            data-testid="current-lineup-section-toggle"
          >
            Current lineups
          </Button>
          {count > 0 && <Chip label={count} size="small" />}
          {(planEntitySummary?.token_count ?? 0) > 0 && (
            <Button
              size="small"
              variant="contained"
              onClick={() => {
                setPlanResolutionFilterCaseId(null);
                setPlanResolutionOpen(true);
              }}
              data-testid="lineup-plan-entity-resolution-open"
            >
              Resolve entities · {planEntitySummary?.token_count} token
              {(planEntitySummary?.token_count ?? 0) === 1 ? '' : 's'}
            </Button>
          )}
          <FormControlLabel
            sx={{ ml: 0.5 }}
            control={
              <Checkbox
                size="small"
                checked={showWorkClosed}
                onChange={(e) => setShowWorkClosed(e.target.checked)}
                data-testid="lineup-show-work-closed-toggle"
              />
            }
            label={<Typography variant="caption">Show work-closed</Typography>}
          />
          {activePlanId != null && (
            <FormControlLabel
              sx={{ ml: 0.5 }}
              control={
                <Checkbox
                  size="small"
                  checked={showAllCases}
                  onChange={(e) => setShowAllCases(e.target.checked)}
                  data-testid="lineup-show-all-toggle"
                />
              }
              label={<Typography variant="caption">Show all (ignore plan)</Typography>}
            />
          )}
          {activePlanId != null &&
            (allowUpload ? (
              <Button
                size="small"
                variant="outlined"
                onClick={() => setUploadOpen(true)}
                data-testid="upload-current-lineup-btn"
              >
                Upload current lineup
              </Button>
            ) : (
              <Tooltip title="Lineup uploads now run through the unified multi-file importer in the Import Center.">
                <Button
                  size="small"
                  variant="outlined"
                  component={NextLink}
                  href="/admin/imports"
                  data-testid="upload-current-lineup-link"
                >
                  Import lineups in Import Center
                </Button>
              </Tooltip>
            ))}
        </Stack>

        <Collapse in={expanded}>
          <Box sx={{ mt: 1 }}>
            {(planEntitySummary?.token_count ?? 0) > 0 && (
              <Alert
                severity="warning"
                sx={{ mb: 1 }}
                action={
                  <Button
                    color="inherit"
                    size="small"
                    onClick={() => {
                      setPlanResolutionFilterCaseId(null);
                      setPlanResolutionOpen(true);
                    }}
                  >
                    Resolve all
                  </Button>
                }
                data-testid="lineup-plan-entity-resolution-banner"
              >
                {planEntitySummary?.token_count} unresolved entity token
                {(planEntitySummary?.token_count ?? 0) === 1 ? '' : 's'} across{' '}
                {planEntitySummary?.eligible_case_count ?? eligibleResolutionCaseIds.length} imported case
                {(planEntitySummary?.eligible_case_count ?? eligibleResolutionCaseIds.length) === 1 ? '' : 's'} — map
                once per token; applies to every matching case.
              </Alert>
            )}
            {isLoading ? (
              <CircularProgress size={20} />
            ) : count === 0 ? (
              <Typography variant="body2" color="text.secondary" data-testid="lineup-empty-state">
                {effectivePlanId != null
                  ? 'No lineup cases for this plan. Toggle “Show all (ignore plan)” to browse every uploaded lineup.'
                  : 'No lineup cases uploaded yet. Upload lineups in the Import Center.'}
              </Typography>
            ) : (
              <Stack spacing={2} data-testid="lineup-case-groups">
                {groupedCases.map((g) => (
                  <Box key={`${g.periodLabel}\u0000${g.productLine}`} data-testid="lineup-case-group">
                    <Stack
                      direction="row"
                      spacing={1}
                      alignItems="center"
                      sx={{ mb: 0.5, mt: 0.5 }}
                    >
                      <Typography variant="subtitle2" data-testid="lineup-group-period">
                        {g.periodLabel}
                      </Typography>
                      <Chip label={g.productLine} size="small" variant="outlined" />
                      <Typography variant="caption" color="text.secondary">
                        {g.cases.length} case{g.cases.length === 1 ? '' : 's'}
                      </Typography>
                    </Stack>
                    <Stack spacing={1}>
                      {g.cases.map((c) => (
                  <Box
                    key={c.id}
                    sx={{
                      border: '1px solid',
                      borderColor: activeCaseId === c.id ? 'primary.main' : 'divider',
                      borderRadius: 1,
                      p: 1,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                      flexWrap: 'wrap',
                    }}
                  >
                    <Typography variant="body2" sx={{ flex: 1, minWidth: 120 }}>
                      {c.file_name ?? '(no file)'}
                      {c.period_label ? ` · ${c.period_label}` : ''}
                    </Typography>
                    <Chip
                      label={lineupCaseStatusLabel(c.commercial_status)}
                      size="small"
                      color={STATUS_COLORS[c.commercial_status] ?? 'default'}
                      data-testid={`lineup-case-status-${c.id}`}
                    />
                    {RESOLUTION_UI_STATUSES.has(c.commercial_status) &&
                      (unresolvedTokenCountByCase.get(c.id) ?? 0) > 0 && (
                        <Chip
                          label={`${unresolvedTokenCountByCase.get(c.id)} unresolved`}
                          size="small"
                          color="warning"
                          variant="outlined"
                          clickable
                          onClick={() => {
                            setPlanResolutionFilterCaseId(c.id);
                            setPlanResolutionOpen(true);
                          }}
                          data-testid={`lineup-case-unresolved-${c.id}`}
                        />
                      )}
                    {(c.iteration_number ?? 1) > 1 && (
                      <Chip
                        label={`Round ${c.iteration_number}`}
                        size="small"
                        variant="outlined"
                        data-testid={`lineup-case-iteration-${c.id}`}
                      />
                    )}
                    <Typography variant="caption" color="text.secondary">
                      {c.line_count} line{c.line_count === 1 ? '' : 's'}
                    </Typography>
                    <Chip
                      label={c.commercial_plan_id != null ? `Plan #${c.commercial_plan_id}` : 'Unlinked'}
                      size="small"
                      variant="outlined"
                      color={c.commercial_plan_id != null ? 'success' : 'default'}
                      data-testid={`lineup-case-link-${c.id}`}
                    />
                    {(c.po_count ?? 0) > 0 && (
                      <Tooltip
                        title={(c.linked_pos ?? [])
                          .map((p) => p.po_number_raw)
                          .join(', ')}
                      >
                        <Chip
                          label={`${c.po_count} PO${(c.po_count ?? 0) === 1 ? '' : 's'}`}
                          size="small"
                          color="secondary"
                          variant="outlined"
                          data-testid={`lineup-case-po-count-${c.id}`}
                        />
                      </Tooltip>
                    )}
                    <Button
                      size="small"
                      variant={activeCaseId === c.id ? 'contained' : 'outlined'}
                      onClick={() => setActiveCaseId(c.id)}
                      data-testid={`lineup-workbench-${c.id}`}
                    >
                      Workbench
                    </Button>
                    <Button size="small" onClick={() => setViewLinesCase(c)}>
                      Details
                    </Button>
                    {activePlanId != null && c.commercial_plan_id !== activePlanId && (
                      <Button
                        size="small"
                        variant="text"
                        onClick={() => attachPlanMutation.mutate({ caseId: c.id, planId: activePlanId })}
                        disabled={attachPlanMutation.isPending}
                        data-testid={`lineup-attach-plan-${c.id}`}
                      >
                        Attach to plan
                      </Button>
                    )}
                    {c.commercial_plan_id != null && (
                      <Button
                        size="small"
                        variant="text"
                        color="inherit"
                        onClick={() => attachPlanMutation.mutate({ caseId: c.id, planId: null })}
                        disabled={attachPlanMutation.isPending}
                        data-testid={`lineup-detach-plan-${c.id}`}
                      >
                        Detach
                      </Button>
                    )}
                    {allowUpload && c.commercial_status === 'draft_imported' && c.line_count === 0 && (
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => setRetryParseCase(c)}
                        data-testid={`retry-parse-open-${c.id}`}
                      >
                        Upload file to this case
                      </Button>
                    )}
                    {(ALLOWED_TRANSITIONS[c.commercial_status]?.length ?? 0) > 0 &&
                      !isSupersededCase(c) && (
                      <Button size="small" onClick={() => setStatusCase(c)}>
                        Update status
                      </Button>
                    )}
                    {c.commercial_status === 'accepted' && (
                      <Button
                        size="small"
                        variant="outlined"
                        color="primary"
                        onClick={() => setSyncCase(c)}
                        data-testid="sync-to-plan-btn"
                      >
                        Sync to plan
                      </Button>
                    )}
                    {RESOLUTION_UI_STATUSES.has(c.commercial_status) && !isSupersededCase(c) && (
                      <Button
                        size="small"
                        variant="text"
                        onClick={() => setAssignDistCase(c)}
                        data-testid={`assign-distributor-btn-${c.id}`}
                      >
                        Assign distributor
                      </Button>
                    )}
                    {isSupersededCase(c) && (
                      <Typography variant="caption" color="text.secondary" data-testid={`superseded-by-${c.id}`}>
                        Superseded by{' '}
                        {c.superseded_by_case_id != null
                          ? caseFileNameById.get(c.superseded_by_case_id) ??
                            `case #${c.superseded_by_case_id}`
                          : 'deleted case'}
                      </Typography>
                    )}
                    {c.commercial_status !== 'cancelled' && !isSupersededCase(c) && (
                      <Button
                        size="small"
                        variant={(c.po_count ?? 0) > 0 ? 'outlined' : 'contained'}
                        color="primary"
                        onClick={() => setConfirmCase(c)}
                        data-testid={`confirm-with-po-btn-${c.id}`}
                      >
                        {(c.po_count ?? 0) > 0 ? 'Add PO' : 'Confirm with PO'}
                      </Button>
                    )}
                    {CLOSE_WORK_STATUSES.has(c.commercial_status) && !isSupersededCase(c) && (
                      <Button
                        size="small"
                        variant="outlined"
                        color="inherit"
                        disabled={closeWorkMutation.isPending}
                        onClick={() => closeWorkMutation.mutate(c.id)}
                        data-testid={`close-lineup-case-work-${c.id}`}
                      >
                        Close case
                      </Button>
                    )}
                    {c.commercial_status === 'draft_imported' && (
                      <Button
                        size="small"
                        color="error"
                        onClick={() => setDeleteCase(c)}
                        disabled={deleteMutation.isPending}
                        data-testid={`lineup-delete-case-${c.id}`}
                      >
                        Delete
                      </Button>
                    )}
                    {(c.po_count ?? 0) > 0 && (
                      <Box sx={{ flexBasis: '100%' }}>
                        <CaseReconciliationInline caseId={c.id} />
                      </Box>
                    )}
                  </Box>
                      ))}
                    </Stack>
                  </Box>
                ))}
              </Stack>
            )}
          </Box>
        </Collapse>

        {activeCaseId != null && activeCase && (
          <Box sx={{ mt: 2 }} data-testid="current-lineup-working-grid">
            {planLineCount === 0 &&
              workingLines.length > 0 &&
              !PO_LINKED_STATUSES.has(activeCase.commercial_status) && (
              <Alert severity="info" sx={{ mb: 1 }}>
                This plan has no commercial planner lines yet. Lineup rows below are staged on this case. Mark the
                case as Ready to sync, then use Sync to plan to create planner lines from eligible rows.
              </Alert>
            )}
            <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
              <Typography variant="subtitle2">
                Current lineup working rows — case #{activeCase.id}
                {activeCase.file_name ? ` · ${activeCase.file_name}` : ''}
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap">
                {RESOLUTION_UI_STATUSES.has(activeCase.commercial_status) && !isSupersededCase(activeCase) && (
                  <>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => setResolutionCase(activeCase)}
                      data-testid="lineup-entity-resolution-open"
                    >
                      Resolve entities
                    </Button>
                    <Button
                      size="small"
                      variant="text"
                      data-testid="lineup-steward-export"
                      onClick={() => {
                        void (async () => {
                          const data = await apiGet<Record<string, unknown>>(
                            `/api/v1/commercial-planner/lineup-cases/${activeCase.id}/steward-export`,
                          );
                          const blob = new Blob([JSON.stringify(data, null, 2)], {
                            type: 'application/json',
                          });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `lineup-case-${activeCase.id}-steward-export.json`;
                          a.click();
                          URL.revokeObjectURL(url);
                        })();
                      }}
                    >
                      Steward export
                    </Button>
                  </>
                )}
                <Button size="small" variant="text" onClick={() => setColSelectorOpen(true)} data-testid="lineup-workbench-columns">
                  Workbench columns
                </Button>
              </Stack>
            </Stack>
            <Dialog
              open={colSelectorOpen}
              onClose={() => setColSelectorOpen(false)}
              maxWidth={false}
              fullWidth
              PaperProps={{ sx: { width: '90vw', maxWidth: 1200, maxHeight: '85vh', m: 2, display: 'flex', flexDirection: 'column' } }}
            >
              <DialogTitle sx={{ pb: 1 }}>
                Workbench columns
                <Typography variant="body2" color="text.secondary" component="span" sx={{ ml: 1 }}>
                  — {visibleColsFiltered.length} selected
                </Typography>
              </DialogTitle>
              <Box sx={{ px: 3, pb: 1, position: 'sticky', top: 0, bgcolor: 'background.paper', zIndex: 1 }}>
                <TextField
                  size="small"
                  placeholder="Search columns…"
                  value={colSelectorSearch}
                  onChange={(e) => setColSelectorSearch(e.target.value)}
                  fullWidth
                />
              </Box>
              <DialogContent dividers sx={{ overflowY: 'auto', flex: 1 }}>
                <Stack spacing={2}>
                  {columnMenuEntries.reduce<Array<{ label: string; cols: string[] }>>(
                    (groups, entry) => {
                      if (entry.kind === 'header') {
                        groups.push({ label: entry.label, cols: [] });
                      } else {
                        const last = groups[groups.length - 1];
                        if (last) last.cols.push(entry.id);
                      }
                      return groups;
                    },
                    [],
                  ).map((group) => {
                    const q = colSelectorSearch.toLowerCase().trim();
                    const cols = q
                      ? group.cols.filter((id) =>
                          workbenchColumnLabel(id, wbMeta).toLowerCase().includes(q),
                        )
                      : group.cols;
                    if (!cols.length) return null;
                    return (
                      <Paper key={group.label} variant="outlined" sx={{ p: 1.5 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                          {group.label}
                        </Typography>
                        <Box
                          sx={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                            gap: 0.5,
                          }}
                        >
                          {cols.map((id) => (
                            <FormControlLabel
                              key={id}
                              control={
                                <Checkbox
                                  size="small"
                                  checked={visibleCols.includes(id)}
                                  onChange={() => {
                                    setVisibleCols((prev) => {
                                      const ix = prev.indexOf(id);
                                      if (ix >= 0) {
                                        if (prev.length <= 1) return prev;
                                        return prev.filter((_, i) => i !== ix);
                                      }
                                      return [...prev, id];
                                    });
                                  }}
                                />
                              }
                              label={
                                <Typography variant="body2" sx={{ fontSize: '0.8rem' }}>
                                  {workbenchColumnLabel(id, wbMeta)}
                                </Typography>
                              }
                            />
                          ))}
                        </Box>
                      </Paper>
                    );
                  })}
                </Stack>
              </DialogContent>
              <DialogActions sx={{ flexWrap: 'wrap', gap: 0.5 }}>
                <Button
                  size="small"
                  onClick={() => {
                    setVisibleCols(defaultUnifiedLineupWorkbenchIds(wbMeta, hasWorkbenchPlan));
                  }}
                  data-testid="lineup-columns-preset-commercial"
                >
                  Lineup template
                </Button>
                <Button
                  size="small"
                  onClick={() => {
                    if (!wbMeta) return;
                    const allow = mergeWorkbenchAllowedIds(wbMeta, hasWorkbenchPlan);
                    const core = defaultWorkbenchVisible(hasWorkbenchPlan).filter((id) => allow.has(id));
                    const proc = pickProcessorPresetWorkbenchIds(wbMeta).filter((id) => allow.has(id));
                    setVisibleCols([...core, ...proc.filter((id) => !core.includes(id))]);
                  }}
                  data-testid="lineup-columns-preset-processor"
                >
                  Processor details
                </Button>
                <Box sx={{ flex: 1 }} />
                <Button size="small" variant="contained" onClick={() => setColSelectorOpen(false)}>
                  Done
                </Button>
              </DialogActions>
            </Dialog>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              Staging flow: Imported → Reviewing → Needs review → Ready to sync → Sync to plan. Resolve
              customer/distributor tokens before marking ready when needed. DAP on rows is import evidence only — not
              landed cost.
            </Typography>
            <Stack direction="row" alignItems="center" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
              <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
                Row filter
              </Typography>
              <ToggleButtonGroup
                size="small"
                exclusive
                value={workbenchScope}
                onChange={(_, v: 'active' | 'synced' | 'ready' | 'blocked' | 'all' | null) => {
                  if (v != null) setWorkbenchScope(v);
                }}
                aria-label="Lineup workbench row filter"
              >
                <ToggleButton value="active">Needs action</ToggleButton>
                <ToggleButton value="ready">Ready to sync</ToggleButton>
                <ToggleButton value="synced">Synced</ToggleButton>
                <ToggleButton value="blocked">Blocked</ToggleButton>
                <ToggleButton value="all">All rows</ToggleButton>
              </ToggleButtonGroup>
            </Stack>
            {activeCase.commercial_plan_id != null && (
              <Stack spacing={1} sx={{ mb: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  Optional fallbacks for sync-eligibility preview (same query params as sync-to-plan preview). Does not
                  change DAP.
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <TextField
                    size="small"
                    label="Fallback customer id"
                    value={wbSync.fallbackCustomerId}
                    onChange={(e) => setWbSync((s) => ({ ...s, fallbackCustomerId: e.target.value }))}
                    sx={{ width: 168 }}
                  />
                  <TextField
                    size="small"
                    label="Fallback distributor id"
                    value={wbSync.fallbackDistributorId}
                    onChange={(e) => setWbSync((s) => ({ ...s, fallbackDistributorId: e.target.value }))}
                    sx={{ width: 176 }}
                  />
                  <TextField
                    size="small"
                    label="Default SRP (local)"
                    value={wbSync.defaultSrpLocal}
                    onChange={(e) => setWbSync((s) => ({ ...s, defaultSrpLocal: e.target.value }))}
                    sx={{ width: 140 }}
                  />
                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={wbSync.allowZeroQuantity}
                        onChange={(e) => setWbSync((s) => ({ ...s, allowZeroQuantity: e.target.checked }))}
                      />
                    }
                    label="Allow zero qty preview"
                  />
                </Stack>
              </Stack>
            )}
            {workbenchCounts && activeCase.commercial_plan_id != null && (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }} data-testid="lineup-workbench-counts">
                <Chip
                  variant="outlined"
                  size="small"
                  label={`Synced to planner: ${workbenchCounts.synced_to_planner}`}
                  color="success"
                />
                {(workbenchCounts.already_in_planner ?? 0) > 0 && (
                  <Chip
                    variant="outlined"
                    size="small"
                    label={`Already in plan (duplicate key): ${workbenchCounts.already_in_planner}`}
                    color="info"
                  />
                )}
                <Chip
                  variant="outlined"
                  size="small"
                  label={`Needs resolution: ${workbenchCounts.needs_resolution}`}
                  color={workbenchCounts.needs_resolution > 0 ? 'warning' : 'default'}
                />
                <Chip variant="outlined" size="small" label={`Ready to sync: ${workbenchCounts.ready_to_sync}`} />
                <Chip variant="outlined" size="small" label={`Blocked from sync: ${workbenchCounts.blocked_from_sync}`} />
                <Chip variant="outlined" size="small" label={`All rows in case: ${workbenchCounts.all_lines}`} />
              </Stack>
            )}
            {workingLines.length === 0 ? (
              workbenchCounts && workbenchCounts.all_lines > 0 && workbenchScope !== 'all' ? (
                <Typography variant="body2" color="text.secondary">
                  No rows in this view. Switch the row filter (for example &quot;All rows&quot;) to inspect synced or
                  blocked lines.
                </Typography>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No rows in the selected case yet. Upload a file or choose another case.
                </Typography>
              )
            ) : (
              <Box data-testid="lineup-workbench-grid">
                <EnterpriseDataGrid
                  rowData={workingLines}
                  columnDefs={wbColumnDefs}
                  gridOptions={wbGridOptions}
                  height={560}
                />
              </Box>
            )}
          </Box>
        )}
      </Box>

      {allowUpload && (
        <UploadLineupDialog
          open={uploadOpen}
          onClose={() => setUploadOpen(false)}
          activePlanId={activePlanId}
          planCountryCode={planCountryCode}
          planCurrencyCode={planCurrencyCode}
          onCreated={() => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] })}
        />
      )}

      {viewLinesCase && (
        <CaseLinesDialog
          open={viewLinesCase != null}
          onClose={() => setViewLinesCase(null)}
          caseId={viewLinesCase.id}
          caseLabel={
            [viewLinesCase.file_name, viewLinesCase.period_label].filter(Boolean).join(' · ') ||
            `Case #${viewLinesCase.id}`
          }
        />
      )}

      {deleteCase && (
        <Dialog
          open={deleteCase != null}
          onClose={() => setDeleteCase(null)}
          maxWidth="sm"
          fullWidth
          data-testid="lineup-delete-case-dialog"
        >
          <DialogTitle>Delete lineup case?</DialogTitle>
          <DialogContent>
            <Stack spacing={1.5} sx={{ mt: 0.5 }}>
              <Typography variant="body2">
                Permanently delete <strong>{deleteCase.file_name ?? `case #${deleteCase.id}`}</strong>?
                This cannot be undone.
              </Typography>
              {deletePreviewQ.isLoading ? (
                <CircularProgress size={20} />
              ) : (deletePreviewQ.data?.superseded_child_count ?? 0) > 0 ? (
                <Alert severity="warning" data-testid="lineup-delete-supersedes-warning">
                  {deletePreviewQ.data?.message ??
                    `This case supersedes ${deletePreviewQ.data?.superseded_child_count} file(s); deleting will restore them as active.`}
                  {(deletePreviewQ.data?.superseded_children ?? []).length > 0 && (
                    <Box component="ul" sx={{ mt: 1, mb: 0, pl: 2 }}>
                      {deletePreviewQ.data!.superseded_children.map((ch) => (
                        <li key={ch.id}>
                          <Typography variant="body2" component="span">
                            {ch.file_name ?? `Case #${ch.id}`}
                          </Typography>
                        </li>
                      ))}
                    </Box>
                  )}
                </Alert>
              ) : null}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button size="small" onClick={() => setDeleteCase(null)} disabled={deleteMutation.isPending}>
              Cancel
            </Button>
            <Button
              size="small"
              color="error"
              variant="contained"
              disabled={deleteMutation.isPending || deletePreviewQ.isLoading}
              onClick={() => deleteMutation.mutate(deleteCase.id)}
              data-testid="lineup-delete-case-confirm"
            >
              {deleteMutation.isPending ? 'Deleting…' : 'Delete case'}
            </Button>
          </DialogActions>
        </Dialog>
      )}

      {statusCase && (
        <StatusTransitionDialog
          open={statusCase != null}
          onClose={() => setStatusCase(null)}
          currentCase={statusCase}
          onConfirm={(status, notes, acceptedBy) => {
            statusMutation.mutate({ caseId: statusCase.id, status, notes, acceptedBy });
          }}
        />
      )}

      {syncCase && (
        <SyncPreviewDialog
          open={syncCase != null}
          onClose={() => setSyncCase(null)}
          caseItem={syncCase}
          onSyncComplete={onSyncComplete}
        />
      )}

      {confirmCase && (
        <ConfirmWithPoDialog
          open={confirmCase != null}
          onClose={() => setConfirmCase(null)}
          currentCase={confirmCase}
          isPending={confirmMutation.isPending}
          error={confirmMutation.isError ? safeDisplayError(confirmMutation.error) : null}
          onConfirm={(poNumbers, notes) =>
            confirmMutation.mutate({ caseId: confirmCase.id, poNumbers, notes })
          }
        />
      )}

      {assignDistCase && (
        <AssignDistributorDialog
          open={assignDistCase != null}
          onClose={() => setAssignDistCase(null)}
          currentCase={assignDistCase}
          isPending={assignDistributorMutation.isPending}
          error={
            assignDistributorMutation.isError
              ? safeDisplayError(assignDistributorMutation.error)
              : null
          }
          onAssign={(payload) =>
            assignDistributorMutation.mutate({ caseId: assignDistCase.id, payload })
          }
        />
      )}

      {allowUpload && retryParseCase && (
        <RetryParseDialog
          open={retryParseCase != null}
          onClose={() => setRetryParseCase(null)}
          targetCase={retryParseCase}
          onParsed={() => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] })}
        />
      )}

      {planResolutionOpen && (
        <LineupEntityResolutionDialog
          open
          onClose={() => {
            setPlanResolutionOpen(false);
            setPlanResolutionFilterCaseId(null);
          }}
          planScope={{
            planId: effectivePlanId,
            caseIds: eligibleResolutionCaseIds,
            filterCaseId: planResolutionFilterCaseId,
          }}
          onApplied={() => {
            void qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
            void qc.invalidateQueries({ queryKey: ['lineup-plan-entity-resolution-candidates'] });
          }}
        />
      )}

      {resolutionCase && (
        <LineupEntityResolutionDialog
          open
          onClose={() => setResolutionCase(null)}
          caseId={resolutionCase.id}
          caseStatus={resolutionCase.commercial_status}
          onApplied={() => {
            void qc.invalidateQueries({ queryKey: ['commercial-lineup-case-lines', resolutionCase.id] });
          }}
        />
      )}
    </>
  );
}
