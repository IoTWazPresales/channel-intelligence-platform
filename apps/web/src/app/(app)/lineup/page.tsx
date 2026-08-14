'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  Link,
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
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, GridOptions, RowClickedEvent } from 'ag-grid-community';
import NextLink from 'next/link';
import type { ChangeEvent } from 'react';
import { useCallback, useMemo, useRef, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';
import { parseLineupImportCsv } from '@/lib/lineupImportCsv';
import { toQueryError } from '@/lib/queryError';

type Row = {
  id: number;
  customer_code: string | null;
  customer_name?: string | null;
  channel_code: string | null;
  period_start: string;
  period_label: string | null;
  product_id?: number | null;
  sku: string | null;
  product_name?: string | null;
  predecessor_sku: string | null;
  successor_sku: string | null;
  current_range_summary: string | null;
  planned_range_summary: string | null;
  planned_launch_date: string | null;
  planned_eol_date: string | null;
  current_volume_units: number | null;
  planned_volume_units: number;
  overlap_cannibalization_flag: boolean;
  whitespace_gap_flag: boolean;
  approval_status: string;
  link_buy_plan_id: number | null;
  link_pricing_id: number | null;
  link_promotion_id: number | null;
  link_budget_request_id: number | null;
  link_roadmap_id: number | null;
  notes?: string | null;
};

type ApplyNetRequirementResponse = {
  inserted: number;
  updated: number;
  skipped: number;
  errors: number;
  skipped_zero_net?: number;
  skipped_no_allocation?: number;
  source_row_count?: number;
  draft_rows_built?: number;
  apply_bias?: boolean;
  commercial_case_id?: number | null;
  commercial_lines_written?: number;
  results?: Array<{ row_index: number; status: string; id?: number; errors: string[] }>;
};

type HalfYearPeriodsResponse = {
  year: number;
  half: number;
  rule?: string;
  periods: Array<{ period_start: string; period_label: string }>;
};

type BuilderEconomicsResponse = {
  oem_sell_in_per_unit?: number;
  profit_per_unit?: number;
  reservation?: {
    total?: number;
    campaign_support?: number;
    non_campaign?: number;
    source?: string;
  };
  treatments?: {
    normal_price_units?: number;
    discount_units?: number;
    normal_price_share?: number;
    note?: string;
  };
  [key: string]: unknown;
};

type BudgetPositionResponse = {
  binding_axis?: string;
  planned_from_lineup_derived?: boolean;
  reservation_source?: string;
  sku_assumption_count?: number;
  planned_line_count?: number;
  derive_diagnostics?: {
    skipped_missing_sku?: number;
    skipped_missing_srp?: number;
    skipped_zero_qty?: number;
  };
  tracks?: {
    money?: {
      planned_reservation_usd?: number;
      drawn_cpor_usd?: number;
      status?: string;
    };
  };
};

const APPROVAL_STATUSES = ['draft', 'pending_approval', 'submitted', 'approved', 'rejected'] as const;

type LineupBulkResponse = {
  inserted: number;
  updated: number;
  skipped: number;
  errors: number;
  results: Array<{ row_index: number; status: string; id?: number; errors: string[] }>;
};

type LineupEventRow = {
  id: number;
  event_type: string;
  old_approval_status: string | null;
  new_approval_status: string | null;
  notes: string | null;
  actor: string | null;
  created_at: string | null;
};

type NetRequirementResponse = {
  data_unavailable?: boolean;
  row_count: number;
  formula?: string;
  horizon_weeks?: number;
  target_cover_weeks?: number;
  rows: Array<{
    distributor_id: number;
    product_id: number;
    business_unit: string | null;
    forecast_demand: number;
    bias_adjusted_forecast: number;
    channel_stock: number;
    in_transit: number;
    target_cover_units: number;
    net_requirement: number;
    weekly_velocity: number;
  }>;
};

export default function LineupPage() {
  const qc = useQueryClient();
  const [patchMsg, setPatchMsg] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [replaceMatching, setReplaceMatching] = useState(false);
  const [importParseMsg, setImportParseMsg] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [applyPeriodStart, setApplyPeriodStart] = useState('2026-04-01');
  const [applyPeriodLabel, setApplyPeriodLabel] = useState('2026Q2');
  const [applyMsg, setApplyMsg] = useState<string | null>(null);
  const [applyBias, setApplyBias] = useState(true);
  const [halfYear, setHalfYear] = useState(2026);
  const [halfSlot, setHalfSlot] = useState<1 | 2>(1);
  const [writeCommercialCase, setWriteCommercialCase] = useState(true);
  const [econSrp, setEconSrp] = useState('');
  const [econResult, setEconResult] = useState<BuilderEconomicsResponse | null>(null);
  const [econError, setEconError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['lineup-items'],
    queryFn: ({ signal }) => apiGet<Row[]>('/api/v1/lineup/items', { signal }),
  });

  const {
    data: netReq,
    isLoading: netReqLoading,
    isError: netReqError,
    refetch: refetchNetReq,
  } = useQuery({
    queryKey: ['lineup-net-requirement', applyBias],
    queryFn: ({ signal }) =>
      apiGet<NetRequirementResponse>(
        `/api/v1/lineup/net-requirement?limit=50&include_customer_shares=false&apply_bias=${applyBias ? 'true' : 'false'}`,
        { signal },
      ),
  });

  const { data: halfYearPeriods } = useQuery({
    queryKey: ['lineup-half-year', halfYear, halfSlot],
    queryFn: ({ signal }) =>
      apiGet<HalfYearPeriodsResponse>(
        `/api/v1/lineup/half-year-periods?year=${halfYear}&half=${halfSlot}`,
        { signal },
      ),
  });

  const budgetPeriod = applyPeriodLabel.trim() || '2026Q2';
  const { data: budgetPos } = useQuery({
    queryKey: ['lineup-budget-position', budgetPeriod],
    queryFn: ({ signal }) =>
      apiGet<BudgetPositionResponse>(
        `/api/v1/lineup/budget-position?period_label=${encodeURIComponent(budgetPeriod)}`,
        { signal },
      ),
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/lineup/items/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lineup-items'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/lineup/items/clear-all', { confirm: true }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['lineup-items'] });
      void qc.invalidateQueries({ queryKey: ['lineup-budget-position'] });
    },
  });

  const bulkImport = useMutation({
    mutationFn: (body: { rows: unknown[]; replace_matching: boolean }) =>
      apiPost<LineupBulkResponse>('/api/v1/lineup/items/bulk', body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['lineup-items'] });
      void qc.invalidateQueries({ queryKey: ['lineup-events'] });
      void qc.invalidateQueries({ queryKey: ['lineup-budget-position'] });
    },
  });

  const applyNetReq = useMutation({
    mutationFn: () =>
      apiPost<ApplyNetRequirementResponse>('/api/v1/lineup/apply-net-requirement', {
        confirm: true,
        period_start: applyPeriodStart,
        period_label: applyPeriodLabel.trim() || null,
        replace_matching: true,
        limit: 200,
        horizon_weeks: 13,
        apply_bias: applyBias,
        write_commercial_case: writeCommercialCase,
      }),
    onSuccess: (res) => {
      const caseBit =
        res.commercial_case_id != null
          ? ` · commercial case #${res.commercial_case_id} (${res.commercial_lines_written ?? 0} lines)`
          : '';
      setApplyMsg(
        `Applied net requirement → draft: inserted ${res.inserted}, updated ${res.updated}, ` +
          `built ${res.draft_rows_built ?? res.inserted + res.updated}, ` +
          `skipped zero-net ${res.skipped_zero_net ?? 0}, no-alloc ${res.skipped_no_allocation ?? 0}` +
          ` · bias=${res.apply_bias ? 'on' : 'off'}${caseBit}`,
      );
      void qc.invalidateQueries({ queryKey: ['lineup-items'] });
      void qc.invalidateQueries({ queryKey: ['lineup-budget-position'] });
    },
    onError: (err) => {
      setApplyMsg(err instanceof Error ? err.message : String(err));
    },
  });

  const builderEcon = useMutation({
    mutationFn: (body: {
      product_id: number;
      net_requirement_units: number;
      target_srp_local: number;
    }) => apiPost<BuilderEconomicsResponse>('/api/v1/lineup/builder-economics', body),
    onSuccess: (res) => {
      setEconResult(res);
      setEconError(null);
    },
    onError: (err) => {
      setEconResult(null);
      setEconError(err instanceof Error ? err.message : String(err));
    },
  });

  const { data: eventRows } = useQuery({
    queryKey: ['lineup-events', selectedId],
    queryFn: ({ signal }) => apiGet<LineupEventRow[]>(`/api/v1/lineup/items/${selectedId}/events`, { signal }),
    enabled: selectedId != null,
  });

  const selectedRow = useMemo(
    () => (data ?? []).find((r) => r.id === selectedId) ?? null,
    [data, selectedId],
  );

  const onCellValueChanged = useCallback(
    async (e: CellValueChangedEvent<Row>) => {
      const id = e.data?.id;
      if (id == null || e.oldValue === e.newValue) return;
      const field = e.colDef.field;
      setPatchMsg(null);
      try {
        if (field === 'approval_status') {
          await apiPatch(`/api/v1/lineup/items/${id}`, {
            approval_status: String(e.newValue ?? ''),
            notes: e.data?.notes ?? null,
          });
        } else if (field === 'notes') {
          await apiPatch(`/api/v1/lineup/items/${id}`, { notes: String(e.newValue ?? '') || null });
        } else {
          return;
        }
        await qc.invalidateQueries({ queryKey: ['lineup-items'] });
      } catch (err) {
        console.error(err);
        setPatchMsg(err instanceof Error ? err.message : String(err));
        await qc.invalidateQueries({ queryKey: ['lineup-items'] });
      }
    },
    [qc]
  );

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'customer_code', headerName: 'Customer', pinned: 'left', minWidth: 120, editable: false },
      {
        field: 'customer_name',
        headerName: 'Customer name',
        minWidth: 160,
        editable: false,
        valueGetter: (p) => p.data?.customer_name ?? '',
      },
      { field: 'channel_code', headerName: 'Channel', minWidth: 100, editable: false },
      { field: 'period_label', headerName: 'Period label', minWidth: 110, editable: false },
      { field: 'period_start', headerName: 'Period start', minWidth: 120, editable: false },
      { field: 'sku', headerName: 'SKU', minWidth: 120, editable: false },
      {
        field: 'product_name',
        headerName: 'Product',
        minWidth: 160,
        editable: false,
        valueGetter: (p) => p.data?.product_name ?? '',
      },
      { field: 'predecessor_sku', headerName: 'Predecessor', minWidth: 120, editable: false },
      { field: 'successor_sku', headerName: 'Successor', minWidth: 120, editable: false },
      { field: 'current_range_summary', headerName: 'Current range', flex: 1, minWidth: 180, editable: false },
      { field: 'planned_range_summary', headerName: 'Planned range', flex: 1, minWidth: 180, editable: false },
      { field: 'planned_launch_date', headerName: 'Launch', minWidth: 120, editable: false },
      { field: 'planned_eol_date', headerName: 'EOL', minWidth: 120, editable: false },
      { field: 'current_volume_units', headerName: 'Vol (current)', minWidth: 130, editable: false },
      { field: 'planned_volume_units', headerName: 'Vol (plan)', minWidth: 120, editable: false },
      { field: 'overlap_cannibalization_flag', headerName: 'Overlap', minWidth: 110, editable: false },
      { field: 'whitespace_gap_flag', headerName: 'Whitespace', minWidth: 120, editable: false },
      {
        field: 'approval_status',
        headerName: 'Approval',
        minWidth: 160,
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: [...APPROVAL_STATUSES] },
      },
      {
        field: 'notes',
        headerName: 'Notes',
        flex: 1,
        minWidth: 200,
        editable: true,
      },
      { field: 'link_buy_plan_id', headerName: 'Buy plan id', minWidth: 120, editable: false },
      { field: 'link_pricing_id', headerName: 'Pricing id', minWidth: 110, editable: false },
      { field: 'link_promotion_id', headerName: 'Promo id', minWidth: 100, editable: false },
      { field: 'link_budget_request_id', headerName: 'Budget req id', minWidth: 130, editable: false },
      { field: 'link_roadmap_id', headerName: 'Roadmap id', minWidth: 110, editable: false },
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending]);

  const onRowClicked = useCallback((e: RowClickedEvent<Row>) => {
    const id = e.data?.id;
    setSelectedId(id != null ? id : null);
    setEconResult(null);
    setEconError(null);
    setEconSrp('');
  }, []);

  const gridOptions: GridOptions<Row> = useMemo(
    () => ({
      singleClickEdit: true,
      onCellValueChanged,
      onRowClicked,
      getRowStyle: (p) =>
        p.data?.id != null && p.data.id === selectedId
          ? { backgroundColor: 'rgba(25, 118, 210, 0.12)' }
          : undefined,
    }),
    [onCellValueChanged, onRowClicked, selectedId]
  );

  const runImport = useCallback(() => {
    setImportParseMsg(null);
    const parsed = parseLineupImportCsv(importText);
    if (parsed.headerErrors.length) {
      setImportParseMsg(parsed.headerErrors.join('\n'));
      return;
    }
    if (parsed.rows.length === 0) {
      setImportParseMsg('No data rows to import after parsing.');
      return;
    }
    const warn =
      parsed.parseWarnings.length > 0
        ? `${parsed.parseWarnings.length} parse warning(s); first: ${parsed.parseWarnings[0]!.message}`
        : null;
    if (warn) setImportParseMsg(warn);
    void bulkImport.mutateAsync({ rows: parsed.rows, replace_matching: replaceMatching }).then(
      () => {
        setImportOpen(false);
        setImportText('');
      },
      (err) => {
        setImportParseMsg(err instanceof Error ? err.message : String(err));
      }
    );
  }, [bulkImport, importText, replaceMatching]);

  const onCsvFile = useCallback((ev: ChangeEvent<HTMLInputElement>) => {
    const f = ev.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setImportText(String(reader.result ?? ''));
    reader.readAsText(f, 'UTF-8');
    ev.target.value = '';
  }, []);

  const rows = data ?? [];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Planning' }, { label: 'Line-up planning' }]} title="Line-up planning" />
      <Alert severity="info" sx={{ mb: 2 }}>
        <Typography variant="body2" component="div">
          <strong>Line-up</strong> is customer / channel / period assortment planning with optional links to buy plans,
          pricing, <Link component={NextLink} href="/promotions">promotions</Link> (see CPOR export tab), budgets, and{' '}
          <Link component={NextLink} href="/roadmap">
            roadmap
          </Link>
          . Net requirement = forecast − channel stock − in-transit + target cover (distributor × product grain). Use{' '}
          <strong>Bulk CSV import</strong> to upsert rows. Click a row for <strong>approval history</strong>.
        </Typography>
      </Alert>
      <Paper sx={{ p: 2, mb: 2 }} data-testid="lineup-net-requirement">
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle1">Net requirement (B2)</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              size="small"
              component="a"
              href={`/api/v1/lineup/net-requirement/export.csv?limit=200&apply_bias=${applyBias ? 'true' : 'false'}`}
              data-testid="lineup-net-requirement-export"
            >
              Export CSV
            </Button>
            <Button
              size="small"
              component="a"
              href={`/api/v1/lineup/net-requirement/export.xlsx?limit=200&apply_bias=${applyBias ? 'true' : 'false'}&period_start=${encodeURIComponent(applyPeriodStart)}&period_label=${encodeURIComponent(applyPeriodLabel)}`}
              data-testid="lineup-net-requirement-export-xlsx"
            >
              Export XLSX
            </Button>
            <Button size="small" onClick={() => void refetchNetReq()} disabled={netReqLoading}>
              Refresh
            </Button>
            <Button
              size="small"
              variant="contained"
              data-testid="lineup-apply-net-requirement"
              disabled={applyNetReq.isPending || !(netReq?.rows?.length)}
              onClick={() => {
                if (
                  !window.confirm(
                    `Apply net requirement into draft lineup for ${applyPeriodLabel} (period_start=${applyPeriodStart})? Matching keys are replaced.${writeCommercialCase ? ' Also writes a commercial_lineup_case.' : ''}`,
                  )
                ) {
                  return;
                }
                setApplyMsg(null);
                void applyNetReq.mutate();
              }}
            >
              {applyNetReq.isPending ? 'Applying…' : 'Apply net requirement'}
            </Button>
          </Stack>
        </Stack>
        <Stack direction="row" spacing={2} sx={{ mb: 1 }} flexWrap="wrap" useFlexGap alignItems="center">
          <FormControl size="small" sx={{ minWidth: 110 }}>
            <InputLabel id="lineup-half-year-label">Year</InputLabel>
            <Select
              labelId="lineup-half-year-label"
              label="Year"
              value={halfYear}
              onChange={(e) => setHalfYear(Number(e.target.value))}
              inputProps={{ 'data-testid': 'lineup-half-year' }}
            >
              {[2025, 2026, 2027].map((y) => (
                <MenuItem key={y} value={y}>
                  {y}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 100 }}>
            <InputLabel id="lineup-half-slot-label">Half</InputLabel>
            <Select
              labelId="lineup-half-slot-label"
              label="Half"
              value={halfSlot}
              onChange={(e) => setHalfSlot(Number(e.target.value) === 2 ? 2 : 1)}
              inputProps={{ 'data-testid': 'lineup-half-slot' }}
            >
              <MenuItem value={1}>1H</MenuItem>
              <MenuItem value={2}>2H</MenuItem>
            </Select>
          </FormControl>
          {(halfYearPeriods?.periods ?? []).map((p) => (
            <Button
              key={`${p.period_start}-${p.period_label}`}
              size="small"
              variant={
                applyPeriodStart === p.period_start && applyPeriodLabel === p.period_label
                  ? 'contained'
                  : 'outlined'
              }
              data-testid={`lineup-period-slot-${p.period_label}`}
              onClick={() => {
                setApplyPeriodStart(p.period_start);
                setApplyPeriodLabel(p.period_label);
              }}
            >
              {p.period_label} ({p.period_start})
            </Button>
          ))}
          <TextField
            size="small"
            label="Apply period start"
            value={applyPeriodStart}
            onChange={(e) => setApplyPeriodStart(e.target.value)}
            inputProps={{ 'data-testid': 'lineup-apply-period-start' }}
            sx={{ width: 160 }}
          />
          <TextField
            size="small"
            label="Period label"
            value={applyPeriodLabel}
            onChange={(e) => setApplyPeriodLabel(e.target.value)}
            inputProps={{ 'data-testid': 'lineup-apply-period-label' }}
            sx={{ width: 140 }}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={applyBias}
                onChange={(_, c) => setApplyBias(c)}
                inputProps={{ 'data-testid': 'lineup-apply-bias' }}
              />
            }
            label="A1 bias on forecast"
            data-testid="lineup-apply-bias-label"
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={writeCommercialCase}
                onChange={(_, c) => setWriteCommercialCase(c)}
                inputProps={{ 'data-testid': 'lineup-write-commercial-case' }}
              />
            }
            label="Write commercial lineup case"
            data-testid="lineup-write-commercial-case-label"
          />
        </Stack>
        {applyMsg ? (
          <Alert
            severity={applyNetReq.isError ? 'warning' : 'success'}
            sx={{ mb: 1 }}
            onClose={() => setApplyMsg(null)}
            data-testid="lineup-apply-result"
          >
            {applyMsg}
          </Alert>
        ) : null}
        {netReqError ? (
          <Alert severity="warning">Could not load net requirement</Alert>
        ) : netReq?.data_unavailable ? (
          <Alert severity="info">Net requirement data unavailable</Alert>
        ) : (
          <>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              Horizon {netReq?.horizon_weeks ?? 13}w · target cover {netReq?.target_cover_weeks ?? 4}w ·{' '}
              {netReq?.row_count ?? 0} pairs · A1 bias {applyBias ? 'ON' : 'OFF'} · stock at dist×product · half-year
              rule {halfYearPeriods?.rule ?? 'uniform_half'}
            </Typography>
            {budgetPos ? (
              <Typography variant="caption" display="block" sx={{ mb: 1 }} data-testid="lineup-budget-position">
                Budget {budgetPeriod} (binding={budgetPos.binding_axis ?? 'money'}
                {budgetPos.planned_from_lineup_derived ? ', lineup-derived' : ''}
                ): reserved {String(budgetPos.tracks?.money?.planned_reservation_usd ?? 0)} · drawn CPOR{' '}
                {String(budgetPos.tracks?.money?.drawn_cpor_usd ?? 0)} USD · status{' '}
                {String(budgetPos.tracks?.money?.status ?? '—')} · sku econ{' '}
                {String(budgetPos.sku_assumption_count ?? 0)} · planned lines{' '}
                {String(budgetPos.planned_line_count ?? 0)} · missing SKU skips{' '}
                {String(budgetPos.derive_diagnostics?.skipped_missing_sku ?? 0)} · missing SRP skips{' '}
                {String(budgetPos.derive_diagnostics?.skipped_missing_srp ?? 0)} · reservation ={' '}
                {String(budgetPos.reservation_source ?? 'derived_from_profit')}
              </Typography>
            ) : null}
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Dist</TableCell>
                  <TableCell>Product</TableCell>
                  <TableCell align="right">Forecast</TableCell>
                  <TableCell align="right">Stock</TableCell>
                  <TableCell align="right">In-transit</TableCell>
                  <TableCell align="right">Target cover</TableCell>
                  <TableCell align="right">Net req</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(netReq?.rows ?? []).slice(0, 15).map((r) => (
                  <TableRow key={`${r.distributor_id}-${r.product_id}`}>
                    <TableCell>{r.distributor_id}</TableCell>
                    <TableCell>{r.product_id}</TableCell>
                    <TableCell align="right">{Math.round(r.forecast_demand)}</TableCell>
                    <TableCell align="right">{Math.round(r.channel_stock)}</TableCell>
                    <TableCell align="right">{Math.round(r.in_transit)}</TableCell>
                    <TableCell align="right">{Math.round(r.target_cover_units)}</TableCell>
                    <TableCell align="right">{Math.round(r.net_requirement)}</TableCell>
                  </TableRow>
                ))}
                {!netReqLoading && (netReq?.rows?.length ?? 0) === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7}>No forecast/stock pairs in horizon</TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </>
        )}
      </Paper>
      {patchMsg ? (
        <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setPatchMsg(null)}>
          {patchMsg}
        </Alert>
      ) : null}
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <Stack spacing={1}>
              <span>
                Rows map to <code>fact_lineup_plan_item</code>. Use <strong>Delete</strong> or{' '}
                <strong>Clear all rows</strong> for demo cleanup. For promo-linked rows, follow export workflow on{' '}
                <Link component={NextLink} href="/promotions">
                  Promotions → CPOR export & approval
                </Link>
                .
              </span>
            </Stack>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No line-up plan rows',
            description:
              'Use Apply net requirement above (when forecast pairs exist), or Bulk CSV import. Rows map to fact_lineup_plan_item.',
            primary: { label: 'Data imports', href: '/admin/imports' },
            secondary: { label: 'Buy plans', href: '/buy-plans' },
          }}
          toolbar={
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['lineup-items'] })}
              onUpload={() => {
                setImportParseMsg(null);
                setImportOpen(true);
              }}
              uploadLabel="Bulk CSV import"
              onClearAll={() => {
                if (!window.confirm('Delete every line-up plan row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              importsHref="/admin/imports"
              busy={delRow.isPending || clearAll.isPending || bulkImport.isPending}
            />
          }
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} gridOptions={gridOptions} />
        </ModuleDataSection>
      </Paper>

      {bulkImport.isSuccess && bulkImport.data ? (
        <Paper sx={{ p: 2, mt: 2 }}>
          <Typography variant="subtitle1" gutterBottom>
            Last import result
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
            <Typography variant="body2">Inserted: {bulkImport.data.inserted}</Typography>
            <Typography variant="body2">Updated: {bulkImport.data.updated}</Typography>
            <Typography variant="body2">Skipped: {bulkImport.data.skipped}</Typography>
            <Typography variant="body2">Row errors: {bulkImport.data.errors}</Typography>
          </Stack>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Batch row #</TableCell>
                <TableCell>Outcome</TableCell>
                <TableCell>Item id</TableCell>
                <TableCell>Detail</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {bulkImport.data.results.map((r) => (
                <TableRow key={`${r.row_index}-${r.status}`}>
                  <TableCell>{r.row_index + 1}</TableCell>
                  <TableCell>{r.status}</TableCell>
                  <TableCell>{r.id ?? '—'}</TableCell>
                  <TableCell>{r.errors?.length ? r.errors.join('; ') : '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Paper sx={{ p: 2, mt: 2 }} data-testid="lineup-builder-economics">
        <Typography variant="subtitle1" gutterBottom>
          Builder economics (profit + reservation)
        </Typography>
        {selectedRow == null ? (
          <Typography variant="body2" color="text.secondary">
            Select a draft grid row, enter target SRP (plan/evidence — never fabricated), then compute.
          </Typography>
        ) : selectedRow.product_id == null ? (
          <Alert severity="warning">Selected row has no product_id — cannot compute economics.</Alert>
        ) : (
          <Stack spacing={1.5}>
            <Typography variant="body2" color="text.secondary">
              Item #{selectedRow.id} · product {selectedRow.product_id} · {selectedRow.sku ?? '—'} · planned vol{' '}
              {selectedRow.planned_volume_units}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <TextField
                size="small"
                label="Target SRP (local)"
                value={econSrp}
                onChange={(e) => setEconSrp(e.target.value)}
                inputProps={{ 'data-testid': 'lineup-econ-srp' }}
                sx={{ width: 180 }}
              />
              <Button
                size="small"
                variant="outlined"
                data-testid="lineup-econ-compute"
                disabled={builderEcon.isPending || !econSrp.trim()}
                onClick={() => {
                  const srp = Number(econSrp);
                  if (!Number.isFinite(srp) || srp <= 0) {
                    setEconError('Enter a positive target SRP');
                    setEconResult(null);
                    return;
                  }
                  void builderEcon.mutate({
                    product_id: Number(selectedRow.product_id),
                    net_requirement_units: Number(selectedRow.planned_volume_units) || 0,
                    target_srp_local: srp,
                  });
                }}
              >
                {builderEcon.isPending ? 'Computing…' : 'Compute reservation'}
              </Button>
            </Stack>
            {econError ? (
              <Alert severity="warning" data-testid="lineup-econ-error">
                {econError.includes('No commercial_sku_assumption') || econError.includes('404')
                  ? `Missing SKU economics for product ${selectedRow.product_id} — seed commercial_sku_assumption first. (${econError})`
                  : econError}
              </Alert>
            ) : null}
            {econResult ? (
              <Box data-testid="lineup-econ-result">
                <Typography variant="body2">
                  Sell-in/unit {String(econResult.oem_sell_in_per_unit ?? '—')} · reservation total{' '}
                  {String(econResult.reservation?.total ?? '—')} · source{' '}
                  {String(econResult.reservation?.source ?? 'derived_from_profit')}
                </Typography>
                {econResult.treatments ? (
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                    Treatments: normal {String(econResult.treatments.normal_price_units ?? '—')} · discount{' '}
                    {String(econResult.treatments.discount_units ?? '—')} · share{' '}
                    {String(econResult.treatments.normal_price_share ?? '—')}
                  </Typography>
                ) : null}
              </Box>
            ) : null}
          </Stack>
        )}
      </Paper>

      <Paper sx={{ p: 2, mt: 2 }}>
        <Typography variant="subtitle1" gutterBottom>
          Approval history
        </Typography>
        {selectedId == null ? (
          <Typography variant="body2" color="text.secondary">
            Select a grid row to load audit events for that line-up item.
          </Typography>
        ) : !eventRows?.length ? (
          <Typography variant="body2" color="text.secondary">
            No approval-change events for item #{selectedId} yet (events are recorded when approval status changes).
          </Typography>
        ) : (
          <Stack spacing={1}>
            <Typography variant="body2" color="text.secondary">
              Latest first for item #{selectedId}.
            </Typography>
            {eventRows.map((ev) => (
              <Box key={ev.id} sx={{ borderLeft: 2, borderColor: 'divider', pl: 1 }}>
                <Typography variant="body2">
                  <strong>{ev.new_approval_status}</strong>
                  {ev.old_approval_status != null ? ` ← ${ev.old_approval_status}` : ''}
                </Typography>
                <Typography variant="caption" color="text.secondary" component="div">
                  {ev.created_at ?? '—'} · {ev.actor ?? 'unknown actor'} · {ev.event_type}
                </Typography>
                {ev.notes ? (
                  <Typography variant="body2" sx={{ mt: 0.5 }}>
                    Notes snapshot: {ev.notes}
                  </Typography>
                ) : null}
              </Box>
            ))}
          </Stack>
        )}
      </Paper>

      <Dialog open={importOpen} onClose={() => !bulkImport.isPending && setImportOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Bulk CSV import</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            First row must be headers (customer_code / Customer, period_start / period, sku / SKU, …). Export XLSX to
            CSV if needed. Without &quot;Replace matching&quot;, existing natural keys are skipped with a reason.
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
            <Button variant="outlined" size="small" onClick={() => fileRef.current?.click()}>
              Choose CSV file
            </Button>
            <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={onCsvFile} />
          </Stack>
          <FormControlLabel
            control={
              <Checkbox
                checked={replaceMatching}
                onChange={(_, c) => setReplaceMatching(c)}
                disabled={bulkImport.isPending}
              />
            }
            label="Replace matching rows (upsert updates in place)"
          />
          <TextField
            multiline
            minRows={10}
            fullWidth
            sx={{ mt: 1 }}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder="customer_code,period_start,sku&#10;ACME,2025-01-01,MY-SKU"
            disabled={bulkImport.isPending}
          />
          {importParseMsg ? (
            <Alert severity="warning" sx={{ mt: 2 }}>
              {importParseMsg}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportOpen(false)} disabled={bulkImport.isPending}>
            Close
          </Button>
          <Button variant="contained" disabled={bulkImport.isPending || !importText.trim()} onClick={() => runImport()}>
            {bulkImport.isPending ? 'Importing…' : 'Run import'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
