'use client';

import {
  Alert,
  Box,
  Button,
  IconButton,
  Popover,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import { useMutation } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, ICellRendererParams } from 'ag-grid-community';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { apiGet, apiPost } from '@/lib/api';

import {
  hydratePlannerRows,
  markDirty,
  mergePromoPlanSuggestions,
  resetField,
  toCreateLines,
  toRecomputeSpecs,
  type DirtyField,
  type PlannerRow,
  type SuggestionLine,
} from './promoPlanDraftMerge';

type DraftPayload = {
  lines?: SuggestionLine[];
  suggested_estimate_qty?: number;
  budget_check?: {
    over_budget_warn?: boolean;
    create_blocked?: boolean;
    planned_from_lineup_derived?: boolean;
    reservation_source?: string;
    tracks?: { money?: { status?: string; planned_reservation_usd?: number; drawn_cpor_usd?: number } };
  };
  comparables?: { count?: number };
};

function formatLeg(leg: Record<string, unknown> | null | undefined): string {
  if (!leg) return '—';
  const qty = leg.qty ?? '—';
  const cost = leg.unit_cost ?? leg.unit_amount ?? leg.unit_cost_proxy ?? '—';
  const asOf = leg.as_of ?? '—';
  return `qty ${String(qty)} · cost ${String(cost)} · as-of ${String(asOf)}`;
}

function MacExplainCell(params: ICellRendererParams<PlannerRow>) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const row = params.data;
  if (!row) return null;
  const intake = row.intake_weighted || {};
  return (
    <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="center" sx={{ width: '100%' }}>
      <IconButton
        size="small"
        data-testid={`b4-mac-popover-${row.product_id}`}
        aria-label="MAC buckets"
        onClick={(e) => {
          e.stopPropagation();
          e.preventDefault();
          setAnchor(e.currentTarget);
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <InfoOutlinedIcon fontSize="small" />
      </IconButton>
      <Popover open={Boolean(anchor)} anchorEl={anchor} onClose={() => setAnchor(null)}>
        <Box sx={{ p: 2, maxWidth: 420 }} data-testid={`b4-mac-popover-body-${row.product_id}`}>
          <Typography variant="subtitle2" gutterBottom>
            Intake-weighted MAC (display legs not in blend)
          </Typography>
          <Typography variant="body2">Bucket A (on-hand): {formatLeg(intake.bucket_a_on_hand)}</Typography>
          <Typography variant="body2">Bucket B (intake): {formatLeg(intake.bucket_b_intake)}</Typography>
          <Typography variant="body2">Planned supply (display): {formatLeg(intake.planned_supply)}</Typography>
          <Typography variant="body2">Sell-out value (display): {formatLeg(intake.sellout_value)}</Typography>
          <Typography variant="body2">Disti cost proxy (display): {formatLeg(intake.disti_cost)}</Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>
            Blend: {String(intake.blend?.formula ?? '—')} = {String(intake.blend?.cost_basis ?? row.suggested_cost_basis ?? '—')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Flags: {(intake.flags || row.flags || []).join(', ') || 'none'}
          </Typography>
        </Box>
      </Popover>
    </Stack>
  );
}

export function PromoPlanBuilderPanel() {
  const [seedCaseId, setSeedCaseId] = useState('');
  const [periodLabel, setPeriodLabel] = useState('2026Q2');
  const [addProductId, setAddProductId] = useState('');
  const [addDistributorId, setAddDistributorId] = useState('');
  const [rows, setRows] = useState<PlannerRow[]>([]);
  const [budgetCheck, setBudgetCheck] = useState<DraftPayload['budget_check']>();
  const [comparableCount, setComparableCount] = useState(0);
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  const [createIsError, setCreateIsError] = useState(false);
  const [draftLoading, setDraftLoading] = useState(false);

  const applyDraft = useCallback((payload: DraftPayload, mode: 'replace' | 'merge') => {
    const incoming = payload.lines ?? [];
    setBudgetCheck(payload.budget_check);
    setComparableCount(payload.comparables?.count ?? 0);
    setRows((prev) => (mode === 'merge' ? mergePromoPlanSuggestions(prev, incoming) : hydratePlannerRows(incoming)));
  }, []);

  const loadDraft = useCallback(
    async (mode: 'replace' | 'merge', extra?: PlannerRow[]) => {
      if (!/^\d+$/.test(seedCaseId)) return;
      setDraftLoading(true);
      try {
        const working = extra ?? rows;
        let payload: DraftPayload;
        if (mode === 'merge' || (extra && extra.length)) {
          payload = await apiPost<DraftPayload>('/api/v1/cpor/intelligence/promo-plan-draft/recompute', {
            seed_case_id: Number(seedCaseId),
            period_label: periodLabel.trim() || null,
            lines: toRecomputeSpecs(working),
          });
        } else {
          payload = await apiGet<DraftPayload>(
            `/api/v1/cpor/intelligence/promo-plan-draft?seed_case_id=${encodeURIComponent(seedCaseId)}&period_label=${encodeURIComponent(periodLabel)}`,
          );
        }
        applyDraft(payload, mode);
      } finally {
        setDraftLoading(false);
      }
    },
    [applyDraft, periodLabel, rows, seedCaseId],
  );

  const createFromDraft = useMutation({
    mutationFn: () =>
      apiPost<Record<string, unknown>>('/api/v1/cpor/intelligence/promo-plan-draft/create-case', {
        seed_case_id: Number(seedCaseId),
        period_label: periodLabel.trim() || null,
        confirm_over_budget: true,
        lines: toCreateLines(rows),
      }),
    onSuccess: (res) => {
      setCreateIsError(false);
      setCreateMsg(
        `Created draft case #${String(res.case_id)} (${String(res.case_code)}) · ${String((res.line_ids as number[] | undefined)?.length ?? 1)} line(s) · budget ${String(res.budget_status)}${res.over_budget_warn ? ' (over-budget warn)' : ''}`,
      );
    },
    onError: (err) => {
      setCreateIsError(true);
      setCreateMsg(err instanceof Error ? err.message : String(err));
    },
  });

  const onCellValueChanged = useCallback((e: CellValueChangedEvent<PlannerRow>) => {
    const field = e.colDef.field as DirtyField | undefined;
    if (!field || e.data == null || e.oldValue === e.newValue) return;
    if (!['estimate_qty', 'cost_basis', 'srp', 'cover_weeks', 'distributor_id', 'pod_quarter'].includes(field)) {
      return;
    }
    setRows((prev) =>
      prev.map((row) => (row.row_key === e.data?.row_key ? markDirty(row, field, e.newValue as never) : row)),
    );
  }, []);

  const colDefs: ColDef<PlannerRow>[] = useMemo(
    () => [
      { field: 'product_sku', headerName: 'SKU', minWidth: 120, editable: false },
      { field: 'product_name', headerName: 'Product', minWidth: 160, editable: false, flex: 1 },
      {
        field: 'distributor_id',
        headerName: 'Distributor',
        minWidth: 110,
        editable: true,
        cellClassRules: { 'cip-cell-dirty': (p) => Boolean(p.data?.dirty_fields.includes('distributor_id')) },
      },
      {
        field: 'pod_quarter',
        headerName: 'POD qtr',
        minWidth: 100,
        editable: true,
        cellClassRules: { 'cip-cell-dirty': (p) => Boolean(p.data?.dirty_fields.includes('pod_quarter')) },
      },
      {
        field: 'estimate_qty',
        headerName: 'Units',
        minWidth: 110,
        editable: true,
        cellClassRules: { 'cip-cell-dirty': (p) => Boolean(p.data?.dirty_fields.includes('estimate_qty')) },
      },
      {
        field: 'cost_basis',
        headerName: 'MAC',
        minWidth: 110,
        editable: true,
        cellClassRules: { 'cip-cell-dirty': (p) => Boolean(p.data?.dirty_fields.includes('cost_basis')) },
        valueFormatter: (p) => (p.value == null || p.value === '' ? '—' : String(p.value)),
      },
      {
        colId: 'mac_explain',
        headerName: 'Buckets',
        minWidth: 88,
        maxWidth: 100,
        editable: false,
        sortable: false,
        filter: false,
        cellRenderer: MacExplainCell,
      },
      {
        field: 'srp',
        headerName: 'SRP',
        minWidth: 110,
        editable: true,
        cellClassRules: { 'cip-cell-dirty': (p) => Boolean(p.data?.dirty_fields.includes('srp')) },
      },
      {
        field: 'cover_weeks',
        headerName: 'Cover wks',
        minWidth: 110,
        editable: true,
        cellClassRules: { 'cip-cell-dirty': (p) => Boolean(p.data?.dirty_fields.includes('cover_weeks')) },
      },
      { field: 'cover_source', headerName: 'Cover src', minWidth: 120, editable: false },
      {
        headerName: 'Reset',
        colId: 'reset',
        minWidth: 90,
        pinned: 'right',
        sortable: false,
        filter: false,
        cellRenderer: (params: ICellRendererParams<PlannerRow>) => {
          const row = params.data;
          if (!row) return null;
          return (
            <IconButton
              size="small"
              data-testid={`b4-reset-row-${row.product_id}`}
              aria-label="Reset to suggested"
              disabled={row.dirty_fields.length === 0}
              onClick={() => {
                setRows((prev) =>
                  prev.map((r) => {
                    if (r.row_key !== row.row_key) return r;
                    return row.dirty_fields.reduce((acc, field) => resetField(acc, field), r);
                  }),
                );
              }}
            >
              <RestartAltIcon fontSize="small" />
            </IconButton>
          );
        },
      },
    ],
    [],
  );

  return (
    <Box
      data-testid="promo-plan-builder-b4"
      sx={{
        '& .cip-cell-dirty': { backgroundColor: 'warning.light' },
      }}
    >
      <Typography variant="subtitle1" sx={{ mb: 1 }}>
        Promo plan builder (B4)
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Seed CPOR case id"
          value={seedCaseId}
          onChange={(e) => setSeedCaseId(e.target.value)}
          inputProps={{ 'data-testid': 'b4-seed-case-id' }}
          sx={{ width: 180 }}
        />
        <TextField
          size="small"
          label="Period label"
          value={periodLabel}
          onChange={(e) => setPeriodLabel(e.target.value)}
          inputProps={{ 'data-testid': 'b4-period-label' }}
          sx={{ width: 140 }}
        />
        <Button
          size="small"
          data-testid="b4-build-draft"
          onClick={() => void loadDraft('replace')}
          disabled={!/^\d+$/.test(seedCaseId) || draftLoading}
        >
          {draftLoading ? 'Building…' : 'Build draft'}
        </Button>
        <Button
          size="small"
          data-testid="b4-refresh-suggestions"
          onClick={() => void loadDraft('merge')}
          disabled={rows.length === 0 || draftLoading}
        >
          Refresh suggestions
        </Button>
        <Button
          size="small"
          variant="contained"
          data-testid="b4-create-case"
          disabled={rows.length === 0 || createFromDraft.isPending || !/^\d+$/.test(seedCaseId)}
          onClick={() => {
            const over = Boolean(budgetCheck?.over_budget_warn);
            if (
              over &&
              !window.confirm(
                'Budget check is over reserved support. Create draft case anyway? (hard enforce may still block server-side)',
              )
            ) {
              return;
            }
            setCreateMsg(null);
            void createFromDraft.mutate();
          }}
        >
          {createFromDraft.isPending ? 'Creating…' : 'Create draft CPOR case'}
        </Button>
        <Button size="small" href="/commercial-planner/cpor-cases">
          Open CPOR Cases
        </Button>
      </Stack>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Add product id"
          value={addProductId}
          onChange={(e) => setAddProductId(e.target.value)}
          inputProps={{ 'data-testid': 'b4-add-product-id' }}
          sx={{ width: 140 }}
        />
        <TextField
          size="small"
          label="Distributor id"
          value={addDistributorId}
          onChange={(e) => setAddDistributorId(e.target.value)}
          inputProps={{ 'data-testid': 'b4-add-distributor-id' }}
          sx={{ width: 140 }}
        />
        <Button
          size="small"
          data-testid="b4-add-line"
          disabled={!/^\d+$/.test(addProductId) || !/^\d+$/.test(seedCaseId)}
          onClick={() => {
            const pid = Number(addProductId);
            const did = /^\d+$/.test(addDistributorId) ? Number(addDistributorId) : null;
            const extra: PlannerRow = {
              row_key: `${pid}:${did ?? ''}:${periodLabel}:new`,
              seed_line_id: null,
              product_id: pid,
              product_sku: null,
              product_name: null,
              distributor_id: did,
              customer_id: null,
              pod_quarter: periodLabel,
              srp: null,
              estimate_qty: 0,
              cost_basis: null,
              cover_weeks: null,
              cover_source: 'tenant_default',
              cover_override: null,
              suggested_srp: null,
              suggested_estimate_qty: 0,
              suggested_cost_basis: null,
              suggested_distributor_id: did,
              suggested_pod_quarter: periodLabel,
              suggested_cover_weeks: null,
              dirty_fields: [],
              intake_weighted: {},
              flags: [],
            };
            const next = [...rows, extra];
            setRows(next);
            setAddProductId('');
            void loadDraft('merge', next);
          }}
        >
          Add line
        </Button>
      </Stack>
      {createMsg ? (
        <Alert
          severity={createIsError ? 'warning' : 'success'}
          sx={{ mb: 1 }}
          onClose={() => setCreateMsg(null)}
          data-testid="b4-create-result"
        >
          {createMsg}
        </Alert>
      ) : null}
      {budgetCheck?.over_budget_warn ? (
        <Alert severity="warning" sx={{ mb: 1 }} data-testid="b4-over-budget-warn">
          Over-budget vs B2 planned reservation (warn only unless hard enforce blocks create).
        </Alert>
      ) : null}
      {rows.length > 0 ? (
        <>
          <Typography variant="body2" component="div" data-testid="b4-draft-summary" sx={{ mb: 1 }}>
            Lines: {rows.length} · comparables: {comparableCount} · budget status{' '}
            {String(budgetCheck?.tracks?.money?.status ?? '—')} · reserved{' '}
            {String(budgetCheck?.tracks?.money?.planned_reservation_usd ?? 0)} · drawn{' '}
            {String(budgetCheck?.tracks?.money?.drawn_cpor_usd ?? 0)} · reservation ={' '}
            {String(budgetCheck?.reservation_source ?? 'derived_from_profit')}
            {budgetCheck?.planned_from_lineup_derived ? ' (lineup-derived)' : ''} · dirty cells survive Refresh
          </Typography>
          <EnterpriseDataGrid
            rowData={rows}
            columnDefs={colDefs}
            height={420}
            gridOptions={{
              getRowId: (p) => p.data.row_key,
              singleClickEdit: true,
              onCellValueChanged,
              stopEditingWhenCellsLoseFocus: true,
            }}
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            Cover weeks here is a session override only — it does not write customer cover policy. Reset restores
            suggested values. MAC buckets are explain-only.
          </Typography>
        </>
      ) : (
        <Typography variant="caption" color="text.secondary">
          Enter a seed case id to compose per-line history units, intake-weighted MAC, and cover. Edits stick across
          Refresh; Reset restores the suggestion.
        </Typography>
      )}
    </Box>
  );
}
