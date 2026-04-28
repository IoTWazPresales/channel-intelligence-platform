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
  InputLabel,
  ListSubheader,
  Menu,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';
import { EntitySearchAutocomplete } from './EntitySearchAutocomplete';

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
  created_at: string | null;
};

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
};

type CaseLinesResponse = {
  lines: CommercialLineupLine[];
  dap_semantics_note: string;
};

type WorkbenchColumnMetadata = {
  case_id: number;
  raw_columns: string[];
  parsed_fields: { id: string; group: string; label: string; field: string }[];
  catalogue_product_fields?: { id: string; group: string; label: string; field: string }[];
  catalogue_spec_keys: string[];
  sync_fields: { id: string; group: string; label: string; field: string }[];
};

const WB_STORAGE_V1 = 'cip.commercial-planner.currentLineupWorkbench.columns.v1';
const WB_STORAGE_V2 = 'cip.commercial-planner.currentLineupWorkbench.columns.v2';

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
  dap: 'DAP evidence',
  issues: 'Status / issues',
  sync: 'Sync preview (plan)',
};

/** Preserve original uploaded header text; default-visible when present for Processor / CPU. */
function pickDefaultProcessorRawColumnIds(rawColumns: string[]): string[] {
  const out: string[] = [];
  const byLower = new Map(rawColumns.map((c) => [c.toLowerCase(), c]));
  for (const pref of ['cpu', 'processor']) {
    const exact = byLower.get(pref);
    if (exact) out.push(`raw:${exact}`);
  }
  return out;
}

function defaultWorkbenchVisible(hasPlan: boolean): string[] {
  const base = [
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
  return s;
}

function readInitialWorkbenchVisible(hasPlan: boolean): string[] {
  const fallback = defaultWorkbenchVisible(hasPlan);
  if (typeof window === 'undefined') return fallback;
  try {
    const v2 = localStorage.getItem(WB_STORAGE_V2);
    if (v2) {
      const arr = JSON.parse(v2) as unknown;
      if (Array.isArray(arr) && arr.every((x) => typeof x === 'string') && arr.length) return arr;
    }
    const raw = localStorage.getItem(WB_STORAGE_V1);
    if (!raw) return fallback;
    const arr = JSON.parse(raw) as unknown;
    if (!Array.isArray(arr)) return fallback;
    const next = arr.filter((x): x is string => typeof x === 'string');
    return next.length ? next : fallback;
  } catch {
    return fallback;
  }
}

function workbenchColumnLabel(colId: string, meta: WorkbenchColumnMetadata | undefined): string {
  if ((CORE_WORKBENCH_IDS as readonly string[]).includes(colId)) {
    return CORE_WORKBENCH_LABELS[colId as CoreWorkbenchId];
  }
  if (colId.startsWith('raw:')) return colId.slice(4);
  if (colId.startsWith('spec:') && meta) {
    const k = colId.slice(5);
    return `Spec: ${k}`;
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
};

type EntityResolutionCandidatesResponse = {
  case_id: number;
  customer_tokens: EntityTokenCandidate[];
  distributor_tokens: EntityTokenCandidate[];
};

const RESOLUTION_UI_STATUSES = new Set(['draft_imported', 'validated', 'pending_review']);

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

// ── Status chip colors ─────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'> =
  {
    draft_imported: 'default',
    validated: 'info',
    pending_review: 'warning',
    accepted: 'success',
    po_pending: 'secondary',
    po_issued: 'secondary',
    in_fulfillment: 'info',
    received_closed: 'default',
    cancelled: 'error',
  };

const ALLOWED_TRANSITIONS: Record<string, string[]> = {
  draft_imported: ['validated', 'cancelled'],
  validated: ['pending_review', 'cancelled'],
  pending_review: ['accepted', 'validated', 'cancelled'],
  accepted: ['po_pending', 'cancelled'],
  po_pending: ['po_issued', 'cancelled'],
  po_issued: ['in_fulfillment'],
  in_fulfillment: ['received_closed'],
  received_closed: [],
  cancelled: [],
};

function buildCaseLinesSearchParams(opts: {
  commercialPlanId: number | null | undefined;
  fallbackCustomerId: string;
  fallbackDistributorId: string;
  defaultSrpLocal: string;
  allowZeroQuantity: boolean;
}): string {
  const p = new URLSearchParams();
  if (!opts.commercialPlanId) return '';
  p.set('include_sync_eligibility', 'true');
  p.set('include_product_specs', 'true');
  p.set('include_line_uploaded', 'true');
  const fc = Number(opts.fallbackCustomerId.trim());
  if (Number.isFinite(fc) && fc > 0) p.set('fallback_customer_id', String(Math.trunc(fc)));
  const fd = Number(opts.fallbackDistributorId.trim());
  if (Number.isFinite(fd) && fd > 0) p.set('fallback_distributor_id', String(Math.trunc(fd)));
  const srp = Number(opts.defaultSrpLocal.trim());
  if (Number.isFinite(srp) && srp > 0) p.set('default_srp_local', String(srp));
  if (opts.allowZeroQuantity) p.set('allow_zero_quantity', 'true');
  return p.toString();
}

function LineupEntityResolutionDialog({
  open,
  onClose,
  caseId,
  caseStatus,
  onApplied,
}: {
  open: boolean;
  onClose: () => void;
  caseId: number;
  caseStatus: string;
  onApplied: () => void;
}) {
  const qc = useQueryClient();
  const [customerPicks, setCustomerPicks] = useState<Record<string, CustomerPick | null>>({});
  const [distributorPicks, setDistributorPicks] = useState<Record<string, DistributorPick | null>>({});
  const [applyError, setApplyError] = useState<string | null>(null);

  const { data, isLoading } = useQuery<EntityResolutionCandidatesResponse>({
    queryKey: ['lineup-entity-resolution-candidates', caseId],
    queryFn: ({ signal }) =>
      apiGet<EntityResolutionCandidatesResponse>(
        `/api/v1/commercial-planner/lineup-cases/${caseId}/entity-resolution-candidates`,
        { signal },
      ),
    enabled: open && RESOLUTION_UI_STATUSES.has(caseStatus),
  });

  useEffect(() => {
    if (!open) {
      setCustomerPicks({});
      setDistributorPicks({});
      setApplyError(null);
    }
  }, [open, caseId]);

  const applyMutation = useMutation({
    mutationFn: async (resolutions: { kind: 'customer' | 'distributor'; token: string; dim_id: number }[]) => {
      await apiPost(`/api/v1/commercial-planner/lineup-cases/${caseId}/entity-resolutions/apply`, {
        resolutions,
      });
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['lineup-entity-resolution-candidates', caseId] });
      await qc.invalidateQueries({ queryKey: ['commercial-lineup-case-lines', caseId] });
      await qc.invalidateQueries({ queryKey: ['lineup-workbench-column-metadata', caseId] });
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
    const resolutions: { kind: 'customer' | 'distributor'; token: string; dim_id: number }[] = [];
    for (const t of data.customer_tokens) {
      const pick = customerPicks[t.token_norm];
      if (pick)
        resolutions.push({ kind: 'customer', token: t.token_display || t.token_norm, dim_id: pick.id });
    }
    for (const t of data.distributor_tokens) {
      const pick = distributorPicks[t.token_norm];
      if (pick)
        resolutions.push({ kind: 'distributor', token: t.token_display || t.token_norm, dim_id: pick.id });
    }
    if (!resolutions.length) {
      setApplyError('Select at least one customer or distributor mapping.');
      return;
    }
    applyMutation.mutate(resolutions);
  };

  const totalUnresolved =
    (data?.customer_tokens.length ?? 0) + (data?.distributor_tokens.length ?? 0);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Resolve lineup entities (this case only)</DialogTitle>
      <DialogContent dividers>
        <Alert severity="info" sx={{ mb: 2 }}>
          Map file tokens to existing customers and distributors. This updates lineup rows only — DAP stays evidence-only
          and is not used as cost.
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
                  Customers ({data.customer_tokens.length})
                </Typography>
                <Stack spacing={2}>
                  {data.customer_tokens.map((t) => (
                    <Box key={`c-${t.token_norm}`}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Token ({t.line_count} row{t.line_count === 1 ? '' : 's'}): {t.token_display}
                      </Typography>
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
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}
            {data.distributor_tokens.length > 0 && (
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Distributors ({data.distributor_tokens.length})
                </Typography>
                <Stack spacing={2}>
                  {data.distributor_tokens.map((t) => (
                    <Box key={`d-${t.token_norm}`}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Token ({t.line_count} row{t.line_count === 1 ? '' : 's'}): {t.token_display}
                      </Typography>
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
                    </Box>
                  ))}
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
          {applyMutation.isPending ? 'Applying…' : 'Apply mappings'}
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
  onSyncComplete?: () => void;
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
      qc.invalidateQueries({ queryKey: ['commercial-lineup-cases'] });
      onSyncComplete?.();
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
                  Skipped — Open Channel account missing (seed dim_customer code OPEN_CHANNEL):{' '}
                  {syncResult.skipped_open_channel_account_missing}
                </Typography>
              )}
            {syncResult.skipped_missing_distributor != null && syncResult.skipped_missing_distributor > 0 && (
              <Typography variant="body2">
                Skipped — distributor required for sync (CommercialPlanLine.distributor_id is not nullable; use
                fallback or map distributor): {syncResult.skipped_missing_distributor}
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
                      Blocked — Open Channel account missing (controlled dim_customer OPEN_CHANNEL not found; run
                      seed): {preview.skipped_open_channel_account_missing}
                    </Typography>
                  )}
                {preview.skipped_missing_distributor != null && preview.skipped_missing_distributor > 0 && (
                  <Typography variant="body2" color="error">
                    Blocked — distributor required for sync (CommercialPlanLine.distributor_id is not nullable; map
                    distributor or use fallback): {preview.skipped_missing_distributor}
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
  const [acceptedBy, setAcceptedBy] = useState('');

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Update status</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Current status: <strong>{currentCase.commercial_status}</strong>
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
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          {nextStatus === 'accepted' && (
            <TextField
              size="small"
              label="Accepted by"
              value={acceptedBy}
              onChange={(e) => setAcceptedBy(e.target.value)}
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
            onConfirm(nextStatus, notes, acceptedBy || undefined);
            onClose();
          }}
        >
          Confirm
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

  const handleClose = () => {
    setFile(null);
    setError(null);
    onClose();
  };

  const handleSubmit = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const parseRes = await fetch(
        `/api/v1/commercial-planner/lineup-cases/${targetCase.id}/parse-upload`,
        { method: 'POST', body: fd },
      );
      if (!parseRes.ok) {
        const errBody = await parseRes.json().catch(() => ({}));
        setError(
          `Parse failed. ${formatHttpErrorDetail(errBody.detail)} You can fix the file and try again.`,
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
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={handleClose}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          onClick={handleSubmit}
          disabled={!file || uploading}
          data-testid="retry-parse-confirm"
        >
          {uploading ? 'Uploading…' : 'Parse file'}
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

  useEffect(() => {
    if (!open) return;
    const cc = (planCountryCode ?? '').trim() || 'ZA';
    const cur = (planCurrencyCode ?? '').trim() || 'ZAR';
    setCountryCode(cc.length <= 3 ? cc.toUpperCase() : 'ZA');
    setCurrencyCode(['ZAR', 'USD'].includes(cur.toUpperCase()) ? cur.toUpperCase() : 'ZAR');
  }, [open, planCountryCode, planCurrencyCode]);

  const handleClose = () => {
    setFile(null);
    setError(null);
    setPeriodLabel('');
    setNotes('');
    onClose();
  };

  const handleCreate = async () => {
    if (!activePlanId) return;
    setCreating(true);
    setError(null);
    try {
      const caseResponse = await apiPost<{ id: number }>('/api/v1/commercial-planner/lineup-cases', {
        commercial_plan_id: activePlanId,
        period_label: periodLabel.trim() || null,
        currency_code: currencyCode,
        country_code: countryCode,
        notes: notes.trim() || null,
      });

      if (file) {
        const fd = new FormData();
        fd.append('file', file);
        const parseRes = await fetch(
          `/api/v1/commercial-planner/lineup-cases/${caseResponse.id}/parse-upload`,
          { method: 'POST', body: fd },
        );
        if (!parseRes.ok) {
          const errBody = await parseRes.json().catch(() => ({}));
          setError(
            `Case created (id=${caseResponse.id}) but file parse failed. ` +
              `The draft case has no lines yet — use "Upload file to this case" on the case card to retry, or delete the draft. ` +
              formatHttpErrorDetail(errBody.detail),
          );
          return;
        }
      }

      onCreated();
      handleClose();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to create lineup case';
      setError(msg);
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
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={handleClose}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          onClick={handleCreate}
          disabled={creating}
          data-testid="upload-lineup-confirm"
        >
          {creating ? 'Creating…' : 'Create'}
        </Button>
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
}: {
  activePlanId: number | null;
  planLineCount?: number;
  planCountryCode?: string | null;
  planCurrencyCode?: string | null;
  onSyncComplete?: () => void;
  onStagedLineupSummary?: (summary: { caseId: number | null; lineCount: number }) => void;
}) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [viewLinesCase, setViewLinesCase] = useState<CommercialLineupCase | null>(null);
  const [statusCase, setStatusCase] = useState<CommercialLineupCase | null>(null);
  const [syncCase, setSyncCase] = useState<CommercialLineupCase | null>(null);
  const [retryParseCase, setRetryParseCase] = useState<CommercialLineupCase | null>(null);
  const [activeCaseId, setActiveCaseId] = useState<number | null>(null);
  const [resolutionCase, setResolutionCase] = useState<CommercialLineupCase | null>(null);
  const [wbSync, setWbSync] = useState({
    fallbackCustomerId: '',
    fallbackDistributorId: '',
    defaultSrpLocal: '',
    allowZeroQuantity: false,
  });
  const [colMenuAnchor, setColMenuAnchor] = useState<null | HTMLElement>(null);

  const { data: cases, isLoading } = useQuery<CommercialLineupCase[]>({
    queryKey: ['commercial-lineup-cases', activePlanId],
    queryFn: ({ signal }) =>
      apiGet<CommercialLineupCase[]>(
        `/api/v1/commercial-planner/lineup-cases?plan_id=${activePlanId}`,
        { signal }
      ),
    enabled: activePlanId != null,
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

  const hasWorkbenchPlan = Boolean(activeCase?.commercial_plan_id);

  const { data: wbMeta, isSuccess: wbMetaReady } = useQuery<WorkbenchColumnMetadata>({
    queryKey: ['lineup-workbench-column-metadata', activeCaseId],
    queryFn: ({ signal }) =>
      apiGet<WorkbenchColumnMetadata>(
        `/api/v1/commercial-planner/lineup-cases/${activeCaseId}/workbench-column-metadata`,
        { signal },
      ),
    enabled: activeCaseId != null && activePlanId != null,
  });

  const allowedWorkbenchIds = useMemo(
    () => mergeWorkbenchAllowedIds(wbMeta, hasWorkbenchPlan),
    [wbMeta, hasWorkbenchPlan],
  );

  const [visibleCols, setVisibleCols] = useState<string[]>([]);
  const processorRawInjectedKey = useRef<string | null>(null);

  useEffect(() => {
    if (activeCaseId == null) {
      setVisibleCols([]);
      return;
    }
    const stored = readInitialWorkbenchVisible(hasWorkbenchPlan);
    const baseAllow = mergeWorkbenchAllowedIds(undefined, hasWorkbenchPlan);
    const prelim = stored.filter((id) => baseAllow.has(id));
    setVisibleCols(prelim.length ? prelim : defaultWorkbenchVisible(hasWorkbenchPlan));
  }, [activeCaseId, hasWorkbenchPlan]);

  useEffect(() => {
    if (activeCaseId == null || !wbMetaReady) return;
    setVisibleCols((prev) => {
      const allow = mergeWorkbenchAllowedIds(wbMeta, hasWorkbenchPlan);
      const next = prev.filter((id) => allow.has(id));
      return next.length ? next : defaultWorkbenchVisible(hasWorkbenchPlan);
    });
  }, [wbMetaReady, wbMeta, activeCaseId, hasWorkbenchPlan]);

  useEffect(() => {
    if (activeCaseId == null || !wbMetaReady || !wbMeta) return;
    const rawCols = wbMeta.raw_columns ?? [];
    const digest = `${activeCaseId}:${rawCols.join('\u0001')}`;
    if (processorRawInjectedKey.current === digest) return;
    const hints = pickDefaultProcessorRawColumnIds(rawCols);
    processorRawInjectedKey.current = digest;
    if (!hints.length) return;
    setVisibleCols((prev) => {
      const allow = mergeWorkbenchAllowedIds(wbMeta, hasWorkbenchPlan);
      const toAdd = hints.filter((id) => allow.has(id) && !prev.includes(id));
      if (!toAdd.length) return prev;
      const dapIdx = prev.indexOf('dap');
      if (dapIdx >= 0) {
        const copy = [...prev];
        copy.splice(dapIdx, 0, ...toAdd);
        return copy;
      }
      return [...toAdd, ...prev];
    });
  }, [activeCaseId, wbMetaReady, wbMeta, hasWorkbenchPlan]);

  useEffect(() => {
    if (typeof window === 'undefined' || !visibleCols.length) return;
    localStorage.setItem(WB_STORAGE_V2, JSON.stringify(visibleCols));
  }, [visibleCols]);

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
      }),
    [
      activeCase?.commercial_plan_id,
      wbSync.fallbackCustomerId,
      wbSync.fallbackDistributorId,
      wbSync.defaultSrpLocal,
      wbSync.allowZeroQuantity,
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
    enabled: activeCaseId != null && activePlanId != null && workingLinesUrl != null,
  });

  const workingLines = workingLinesData?.lines ?? [];

  const syncSummary = useMemo(() => {
    if (!workingLines.length || !activeCase?.commercial_plan_id) return null;
    const first = workingLines[0];
    if (typeof first.sync_eligible !== 'boolean') return null;
    let eligible = 0;
    const reasons: Record<string, number> = {};
    for (const ln of workingLines) {
      if (ln.sync_eligible) eligible += 1;
      else if (ln.sync_skip_reason) {
        reasons[ln.sync_skip_reason] = (reasons[ln.sync_skip_reason] ?? 0) + 1;
      }
    }
    return { eligible, reasons, total: workingLines.length };
  }, [workingLines, activeCase?.commercial_plan_id]);

  const showSyncWorkbenchCol = useMemo(
    () =>
      Boolean(activeCase?.commercial_plan_id) &&
      workingLines.length > 0 &&
      typeof workingLines[0]?.sync_eligible === 'boolean',
    [activeCase?.commercial_plan_id, workingLines],
  );

  useEffect(() => {
    onStagedLineupSummary?.({ caseId: activeCaseId, lineCount: workingLines.length });
  }, [activeCaseId, workingLines.length, onStagedLineupSummary]);

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
      await qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] });
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
        return ln.dap_evidence_local != null ? ln.dap_evidence_local.toLocaleString() : '—';
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
        const specs =
          ln.product_specs && typeof ln.product_specs === 'object' && !Array.isArray(ln.product_specs)
            ? (ln.product_specs as Record<string, unknown>)
            : {};
        const v = specs[k];
        if (v == null || (typeof v === 'string' && !v.trim())) return '—';
        return String(v);
      }
      if (colId.startsWith('sync:')) {
        const field = colId.slice(5);
        return formatSyncFieldForWorkbench(ln, field);
      }
      return '—';
    },
    [activeCaseId, patchLineMutation, showSyncWorkbenchCol],
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (caseId: number) =>
      apiDelete(`/api/v1/commercial-planner/lineup-cases/${caseId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] }),
  });

  const count = cases?.length ?? 0;

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
          {activePlanId != null && (
            <Button
              size="small"
              variant="outlined"
              onClick={() => setUploadOpen(true)}
              data-testid="upload-current-lineup-btn"
            >
              Upload current lineup
            </Button>
          )}
        </Stack>

        <Collapse in={expanded}>
          <Box sx={{ mt: 1 }}>
            {isLoading ? (
              <CircularProgress size={20} />
            ) : count === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No current lineup cases for this plan.
              </Typography>
            ) : (
              <Stack spacing={1}>
                {cases!.map((c) => (
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
                      label={c.commercial_status}
                      size="small"
                      color={STATUS_COLORS[c.commercial_status] ?? 'default'}
                    />
                    <Typography variant="caption" color="text.secondary">
                      {c.line_count} line{c.line_count === 1 ? '' : 's'}
                    </Typography>
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
                    {c.commercial_status === 'draft_imported' && c.line_count === 0 && (
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => setRetryParseCase(c)}
                        data-testid={`retry-parse-open-${c.id}`}
                      >
                        Upload file to this case
                      </Button>
                    )}
                    {(ALLOWED_TRANSITIONS[c.commercial_status]?.length ?? 0) > 0 && (
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
                    {c.commercial_status === 'draft_imported' && (
                      <Button
                        size="small"
                        color="error"
                        onClick={() => deleteMutation.mutate(c.id)}
                        disabled={deleteMutation.isPending}
                      >
                        Delete
                      </Button>
                    )}
                  </Box>
                ))}
              </Stack>
            )}
          </Box>
        </Collapse>

        {activeCaseId != null && activeCase && (
          <Box sx={{ mt: 2 }} data-testid="current-lineup-working-grid">
            {planLineCount === 0 && workingLines.length > 0 && (
              <Alert severity="info" sx={{ mb: 1 }}>
                This plan has no commercial planner lines yet. Lineup rows below are staged on this case. Accept the
                case, then use Sync to plan to create planner lines from eligible rows.
              </Alert>
            )}
            <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
              <Typography variant="subtitle2">
                Current lineup working rows — case #{activeCase.id}
                {activeCase.file_name ? ` · ${activeCase.file_name}` : ''}
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap">
                {RESOLUTION_UI_STATUSES.has(activeCase.commercial_status) && (
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => setResolutionCase(activeCase)}
                    data-testid="lineup-entity-resolution-open"
                  >
                    Resolve entities
                  </Button>
                )}
                <Button size="small" variant="text" onClick={(e) => setColMenuAnchor(e.currentTarget)} data-testid="lineup-workbench-columns">
                  Workbench columns
                </Button>
              </Stack>
            </Stack>
            <Menu anchorEl={colMenuAnchor} open={Boolean(colMenuAnchor)} onClose={() => setColMenuAnchor(null)}>
              {columnMenuEntries.map((entry, idx) =>
                entry.kind === 'header' ? (
                  <ListSubheader key={`h-${entry.label}-${idx}`} sx={{ lineHeight: 2 }}>
                    {entry.label}
                  </ListSubheader>
                ) : (
                  <MenuItem key={entry.id} disableRipple sx={{ py: 0 }}>
                    <FormControlLabel
                      control={
                        <Checkbox
                          size="small"
                          checked={visibleCols.includes(entry.id)}
                          onChange={() => {
                            setVisibleCols((prev) => {
                              const ix = prev.indexOf(entry.id);
                              if (ix >= 0) {
                                if (prev.length <= 1) return prev;
                                return prev.filter((_, i) => i !== ix);
                              }
                              return [...prev, entry.id];
                            });
                          }}
                        />
                      }
                      label={workbenchColumnLabel(entry.id, wbMeta)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </MenuItem>
                ),
              )}
            </Menu>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              Case lifecycle: draft → validated → pending review → accepted → sync creates planner lines. Resolve
              customer/distributor tokens before accept when needed. DAP on rows is import evidence only — not landed
              cost.
            </Typography>
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
            {syncSummary && (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                <Chip
                  variant="outlined"
                  size="small"
                  color="success"
                  label={`Sync-eligible rows: ${syncSummary.eligible} / ${syncSummary.total}`}
                  data-testid="lineup-workbench-sync-eligible-chip"
                />
                {Object.entries(syncSummary.reasons).map(([k, v]) => (
                  <Chip key={k} variant="outlined" size="small" label={`${k}: ${v}`} />
                ))}
              </Stack>
            )}
            {workingLines.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No rows in the selected case yet. Upload a file or choose another case.
              </Typography>
            ) : (
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      {visibleColsFiltered.map((colId) => (
                        <TableCell key={colId}>{workbenchColumnLabel(colId, wbMeta)}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {workingLines.map((ln) => {
                      const canEdit = activeCase.commercial_status === 'draft_imported';
                      return (
                        <TableRow key={ln.id}>
                          {visibleColsFiltered.map((colId) => (
                            <TableCell key={`${ln.id}-${colId}`}>{wbCellContent(ln, colId, canEdit)}</TableCell>
                          ))}
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </Box>
            )}
          </Box>
        )}
      </Box>

      <UploadLineupDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        activePlanId={activePlanId}
        planCountryCode={planCountryCode}
        planCurrencyCode={planCurrencyCode}
        onCreated={() => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] })}
      />

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

      {retryParseCase && (
        <RetryParseDialog
          open={retryParseCase != null}
          onClose={() => setRetryParseCase(null)}
          targetCase={retryParseCase}
          onParsed={() => qc.invalidateQueries({ queryKey: ['commercial-lineup-cases', activePlanId] })}
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
