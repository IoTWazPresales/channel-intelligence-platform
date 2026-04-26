'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  InputLabel,
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
import type { CellValueChangedEvent, ColDef, GridOptions } from 'ag-grid-community';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
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
  target_units: number;
  target_srp_local: number;
  promo_srp_local: number | null;
  promo_mix_pct: number;
  calc_sell_in_price_usd: number | null;
  calc_buy_price_usd: number | null;
  calc_promo_reserve_usd: number | null;
  calc_non_promo_reserve_usd: number | null;
  calc_internal_gp_usd: number | null;
  calc_flags: string[];
  calc_explanation: string | null;
};

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };
type ProductPick = { id: number; sku: string; name: string };

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
};

type Summary = {
  line_count: number;
  total_units: number;
  total_internal_gp_usd: number;
  total_promo_reserve_usd: number;
  total_non_promo_reserve_usd: number;
  flags: string[];
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
  dap_local: number | null;
  disti_margin_pct: number | null;
  customer_token: string | null;
  diagnostic_codes: string[];
  has_warnings: boolean;
  has_unknown_customer: boolean;
  period_label: string | null;
  country_code: string | null;
  currency_code: string | null;
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

  const { data: plans, isLoading, isError, error } = useQuery({
    queryKey: ['commercial-plans'],
    queryFn: ({ signal }) => apiGet<Plan[]>('/api/v1/commercial-planner/plans', { signal }),
  });

  const { data: lineupJobs } = useQuery({
    queryKey: ['lineup-jobs'],
    queryFn: ({ signal }) => apiGet<LineupJob[]>('/api/v1/commercial-planner/lineup-jobs', { signal }),
    enabled: tab === 2,
  });

  const { data: coverageLines, isLoading: coverageLoading } = useQuery({
    queryKey: ['lineup-coverage', lineupJobId],
    queryFn: ({ signal }) =>
      apiGet<LineupCoverageLine[]>(
        `/api/v1/commercial-planner/lineup-coverage?job_id=${lineupJobId}`,
        { signal }
      ),
    enabled: lineupJobId != null && tab === 2,
  });

  const activePlanId = selectedPlanId ?? plans?.[0]?.id ?? null;
  const { data: lines } = useQuery({
    queryKey: ['commercial-plan-lines', activePlanId],
    queryFn: ({ signal }) => apiGet<PlanLine[]>(`/api/v1/commercial-planner/plans/${activePlanId}/lines`, { signal }),
    enabled: activePlanId != null,
  });
  const { data: summary } = useQuery({
    queryKey: ['commercial-plan-summary', activePlanId],
    queryFn: ({ signal }) => apiGet<Summary>(`/api/v1/commercial-planner/plans/${activePlanId}/summary`, { signal }),
    enabled: activePlanId != null,
  });
  const { data: suggestions } = useQuery({
    queryKey: ['commercial-plan-suggestions', activePlanId],
    queryFn: ({ signal }) => apiGet<SuggestionBundle[]>(`/api/v1/commercial-planner/plans/${activePlanId}/suggestions`, { signal }),
    enabled: activePlanId != null,
  });

  const lineById = useMemo(() => new Map((lines ?? []).map((l) => [l.id, l])), [lines]);

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
  const recalc = useMutation({
    mutationFn: () => apiPost(`/api/v1/commercial-planner/plans/${activePlanId}/recalculate`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-plan-lines', activePlanId] });
      void qc.invalidateQueries({ queryKey: ['commercial-plan-summary', activePlanId] });
    },
  });
  const applySuggestion = useMutation({
    mutationFn: (payload: { line_id: number; suggestion_type: string; value: unknown }) =>
      apiPost('/api/v1/commercial-planner/apply-suggestion', payload),
    onSuccess: () => {
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
      await apiPatch(`/api/v1/commercial-planner/lines/${lineId}`, { [f]: e.newValue });
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
        minWidth: 200,
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
        minWidth: 200,
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          const bits = [d.distributor_code, d.distributor_name].filter(Boolean);
          return bits.length ? bits.join(' — ') : `#${d.distributor_id}`;
        },
      },
      {
        colId: 'product_display',
        headerName: 'Product',
        minWidth: 200,
        valueGetter: (p) => {
          const d = p.data;
          if (!d) return '';
          const bits = [d.product_sku, d.product_name].filter(Boolean);
          return bits.length ? bits.join(' — ') : `#${d.product_id}`;
        },
      },
      {
        headerName: 'Entities',
        minWidth: 100,
        sortable: false,
        filter: false,
        cellRenderer: ({ data }: { data: PlanLine }) =>
          data ? (
            <Button size="small" variant="outlined" onClick={() => openEditLine(data)}>
              Edit
            </Button>
          ) : null,
      },
      { field: 'target_units', headerName: 'Units', editable: true, type: 'numericColumn', minWidth: 100 },
      { field: 'target_srp_local', headerName: 'Target SRP', editable: true, type: 'numericColumn', minWidth: 110 },
      { field: 'promo_srp_local', headerName: 'Promo SRP', editable: true, type: 'numericColumn', minWidth: 110 },
      { field: 'promo_mix_pct', headerName: 'Promo mix', editable: true, type: 'numericColumn', minWidth: 110 },
      { field: 'calc_sell_in_price_usd', headerName: 'Sell-in USD', minWidth: 120 },
      { field: 'calc_buy_price_usd', headerName: 'Buy USD', minWidth: 120 },
      { field: 'calc_internal_gp_usd', headerName: 'Internal GP', minWidth: 120 },
      { field: 'calc_promo_reserve_usd', headerName: 'Promo reserve', minWidth: 130 },
      { field: 'calc_non_promo_reserve_usd', headerName: 'Non-promo reserve', minWidth: 150 },
      { field: 'calc_flags', headerName: 'Flags', minWidth: 240, valueGetter: (p) => (p.data?.calc_flags ?? []).join(', ') },
      {
        headerName: 'Delete',
        minWidth: 90,
        cellRenderer: ({ data }: { data: PlanLine }) =>
          data ? (
            <Button size="small" color="error" onClick={() => void deleteLine.mutate(data.id)}>
              Delete
            </Button>
          ) : null,
      },
    ],
    [deleteLine, openEditLine]
  );

  const lineGrid: GridOptions<PlanLine> = useMemo(
    () => ({
      singleClickEdit: true,
      onCellValueChanged: (e) => void onLineCell(e),
    }),
    [onLineCell]
  );

  const plansPanel = (
    <>
      <Paper sx={{ p: 2, mb: 2 }}>
        <ModuleDataSection
          intro="Choose a plan below, add lines with the builder (search picks master data), recalculate for deterministic economics, then use suggestions if you want assisted tweaks."
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void qc.invalidateQueries({ queryKey: ['commercial-plans'] })}
          isEmpty={(plans ?? []).length === 0}
          empty={{
            title: 'No commercial plans yet',
            description: 'Create a plan to start manual lineup and economics planning.',
            primary: { label: 'Create first plan', href: '/commercial-planner' },
          }}
          toolbar={
            <ModuleGridToolbar
              onAdd={() => setAddPlanOpen(true)}
              onRefresh={() => void qc.invalidateQueries({ queryKey: ['commercial-plans'] })}
              onClearAll={undefined}
              busy={createPlan.isPending}
            />
          }
        >
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {(plans ?? []).map((p) => (
              <Button key={p.id} variant={activePlanId === p.id ? 'contained' : 'outlined'} onClick={() => setSelectedPlanId(p.id)}>
                {p.plan_name} ({p.status})
              </Button>
            ))}
          </Stack>
        </ModuleDataSection>
      </Paper>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} alignItems="stretch">
        <Box sx={{ flex: 3 }}>
          <Paper sx={{ p: 2, mb: 2 }}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
              <Button variant="contained" onClick={() => setAddLineOpen(true)} disabled={activePlanId == null}>
                Add line
              </Button>
              <Button variant="outlined" onClick={() => recalc.mutate()} disabled={activePlanId == null || recalc.isPending}>
                Recalculate
              </Button>
              <Typography variant="caption" color="text.secondary" sx={{ flex: '1 1 220px', minWidth: 0 }}>
                Selectors for customer / distributor / product appear inside <strong>Add line</strong> and <strong>Edit</strong> — type
                to search master data.
              </Typography>
            </Stack>
            <EnterpriseDataGrid rowData={lines ?? []} columnDefs={lineCols} gridOptions={lineGrid} height={480} />
          </Paper>
          {(summary?.flags?.length ?? 0) > 0 ? (
            <Alert severity="warning">Plan flags: {summary?.flags.join(', ')}</Alert>
          ) : (
            <Alert severity="success">No blocking economics flags detected.</Alert>
          )}
        </Box>
        <Box sx={{ flex: 2 }}>
          <Paper sx={{ p: 2, mb: 2 }}>
            <Typography variant="subtitle1">Plan summary</Typography>
            <Typography variant="body2">Lines: {summary?.line_count ?? 0}</Typography>
            <Typography variant="body2">Units: {summary?.total_units ?? 0}</Typography>
            <Typography variant="body2">Internal GP USD: {summary?.total_internal_gp_usd ?? 0}</Typography>
            <Typography variant="body2">Promo reserve USD: {summary?.total_promo_reserve_usd ?? 0}</Typography>
            <Typography variant="body2">Non-promo reserve USD: {summary?.total_non_promo_reserve_usd ?? 0}</Typography>
          </Paper>
          <Paper sx={{ p: 2 }}>
            <Typography variant="subtitle1" sx={{ mb: 0.5 }}>
              Assisted suggestions
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              Heuristics from history and forecasts — optional. Applying updates the line; use Recalculate when you need refreshed
              dollar outputs.
            </Typography>
            <Stack spacing={1}>
              {(suggestions ?? []).flatMap((bundle) =>
                bundle.suggestions
                  .map((s, idx) => ({ bundle, s, key: `${bundle.line_id}-${s.type}-${idx}` }))
                  .filter((x) => !dismissed[x.key])
                  .map(({ bundle, s, key }) => {
                    const ln = lineById.get(bundle.line_id);
                    const label = lineEntitySummary(ln) || `Line #${bundle.line_id}`;
                    return (
                      <Paper key={key} variant="outlined" sx={{ p: 1 }}>
                        <Typography variant="body2">
                          <strong>{label}</strong> · {s.type} · {s.confidence}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" display="block">
                          {s.reason}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Factors: {Object.keys(s.factors).join(', ')}
                        </Typography>
                        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                          <Button
                            size="small"
                            variant="contained"
                            onClick={() =>
                              applySuggestion.mutate({
                                line_id: bundle.line_id,
                                suggestion_type: s.type,
                                value: s.value,
                              })
                            }
                          >
                            Apply
                          </Button>
                          <Button size="small" onClick={() => setDismissed((prev) => ({ ...prev, [key]: true }))}>
                            Dismiss
                          </Button>
                        </Stack>
                      </Paper>
                    );
                  })
              )}
              {!suggestions?.length ? <Typography color="text.secondary">No suggestions available yet.</Typography> : null}
            </Stack>
          </Paper>
        </Box>
      </Stack>

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
              getOptionLabel={(o) => `${o.sku || '—'} — ${o.name || ''}`}
              disabled={createLine.isPending}
              helperText="Type SKU or product name to search the catalog."
            />
            <Divider />
            <TextField label="Target units" value={lineDraft.target_units} onChange={(e) => setLineDraft((p) => ({ ...p, target_units: e.target.value }))} />
            <TextField
              label="Target SRP local"
              value={lineDraft.target_srp_local}
              onChange={(e) => setLineDraft((p) => ({ ...p, target_srp_local: e.target.value }))}
            />
            <TextField
              label="Promo SRP local"
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
              getOptionLabel={(o) => `${o.sku || '—'} — ${o.name || ''}`}
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
        <InputLabel id="lineup-job-select-label">Select a lineup import job</InputLabel>
        <Select
          labelId="lineup-job-select-label"
          value={lineupJobId ?? ''}
          label="Select a lineup import job"
          inputProps={{ 'data-testid': 'lineup-job-select' }}
          onChange={(e) => setLineupJobId((e.target.value as number) || null)}
        >
          {(lineupJobs ?? []).map((j) => (
            <MenuItem key={j.id} value={j.id}>
              {j.period_label ?? j.file_name} — {j.line_count} line{j.line_count !== 1 ? 's' : ''}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {/* Summary cards */}
      {lineupSummary ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap data-testid="lineup-summary-cards">
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

      {/* Line data table */}
      {lineupJobId == null ? (
        <Typography variant="body2" color="text.disabled" data-testid="lineup-empty-state">
          Select a lineup import job above to view loaded line data.
        </Typography>
      ) : coverageLoading ? (
        <Typography variant="body2" color="text.secondary">
          Loading…
        </Typography>
      ) : coverageLines && coverageLines.length > 0 ? (
        <Box sx={{ overflowX: 'auto' }} data-testid="lineup-coverage-table">
          <Table size="small" sx={{ minWidth: 900 }}>
            <TableHead>
              <TableRow>
                <TableCell>Row</TableCell>
                <TableCell>Product SKU</TableCell>
                <TableCell>Model</TableCell>
                <TableCell>Part #</TableCell>
                <TableCell>Base unit</TableCell>
                <TableCell>Customer</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">MSRP</TableCell>
                <TableCell align="right">Promo</TableCell>
                <TableCell align="right">DAP</TableCell>
                <TableCell align="right">Disti %</TableCell>
                <TableCell>⚠</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {coverageLines.map((ln) => (
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
                  <TableCell align="right" data-testid={`disti-margin-${ln.id}`}>
                    {fmtMarginPct(ln.disti_margin_pct)}
                  </TableCell>
                  <TableCell>{ln.has_warnings ? '⚠' : ''}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      ) : coverageLines ? (
        <Typography variant="body2" color="text.disabled" data-testid="lineup-no-lines">
          No lineup lines found for this job.
        </Typography>
      ) : null}
    </Stack>
  );

  return (
    <>
      <PageHeader crumbs={[{ label: 'Commercial' }, { label: 'Planner' }]} title="Commercial planner" />
      <Alert severity="info" sx={{ mb: 2 }} data-testid="commercial-planner-workflow-guide">
        <Typography variant="body2" component="div" sx={{ '& ul': { m: 0, pl: 2.5 }, '& li': { mb: 0.5 } }}>
          <strong>How this workspace fits together</strong>
          <ul>
            <li>
              <strong>Plans & lines</strong> — Pick a plan, then use <strong>Add line</strong> to open the builder. Customer,
              distributor, and product are <strong>searchable pick lists</strong> (not raw IDs). Use <strong>Edit</strong> on a row
              to change those entities. Edit units and prices in the grid; then press <strong>Recalculate</strong> to persist economics.
            </li>
            <li>
              <strong>Planner defaults</strong> — One row per customer, distributor, and SKU for margins, rebates, landed cost, VAT,
              FX, and reserves. Economics read these unless a line sets an explicit override. After changing defaults, click{' '}
              <strong>Recalculate</strong> so stored line calcs match.
            </li>
            <li>
              <strong>Assisted suggestions</strong> — Optional hints from history and forecasts. <strong>Apply</strong> writes the
              suggestion to the line; recalculate again if you need updated dollars.
            </li>
          </ul>
        </Typography>
      </Alert>
      <Paper sx={{ px: 2, pt: 1, mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} aria-label="Commercial planner sections">
          <Tab label="Plans & lines" id="commercial-planner-tab-plans" aria-controls="commercial-planner-panel-plans" />
          <Tab
            label="Planner defaults"
            id="commercial-planner-tab-defaults"
            aria-controls="commercial-planner-panel-defaults"
          />
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
              : 'commercial-planner-panel-lineup'
        }
        aria-labelledby={
          tab === 0
            ? 'commercial-planner-tab-plans'
            : tab === 1
              ? 'commercial-planner-tab-defaults'
              : 'commercial-planner-tab-lineup'
        }
      >
        {tab === 0 ? plansPanel : tab === 1 ? <PlannerDefaultsMaintenance /> : lineupCoveragePanel}
      </div>
    </>
  );
}
