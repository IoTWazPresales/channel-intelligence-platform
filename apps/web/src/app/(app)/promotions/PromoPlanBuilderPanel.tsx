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
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, ICellRendererParams } from 'ag-grid-community';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { invalidateAfterCaseWrite } from '@/features/promotions-funding/calendarClashKeys';
import { useLineIdentifierPreference } from '@/features/tenant/useLineIdentifierPreference';
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
  type PromotionEvidence,
  type SuggestionLine,
} from './promoPlanDraftMerge';

function sellthroughCaption(evidence?: PromotionEvidence | null): string {
  if (evidence?.read_failed) return 'Sell-through evidence unavailable';
  const cover = evidence?.observed_cover;
  if (cover?.weeks == null) return 'Customer cover: Not available yet';
  return `Customer cover ${cover.weeks}w${cover.flag === 'high_cover' ? ' (high)' : ''}`;
}

type DraftPayload = {
  lines?: SuggestionLine[];
  suggested_estimate_qty?: number | null;
  budget_check?: {
    over_budget_warn?: boolean;
    create_blocked?: boolean;
    planned_from_lineup_derived?: boolean;
    reservation_source?: string;
    drawn_source?: string;
    reservation_not_available_reason?: string | null;
    tracks?: {
      money?: { status?: string; planned_reservation_usd?: number | null; drawn_cpor_usd?: number };
    };
  };
};

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
        aria-label="Cost evidence"
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
            Cost from this customer’s sell-through
          </Typography>
          <Typography variant="body2">
            Cost: {String(intake.cost_basis ?? row.suggested_cost_basis ?? 'Not available yet')}
          </Typography>
          <Typography variant="body2">
            Field: {String(intake.evidence?.field_used ?? '—')} · reported week: {String(intake.evidence?.as_of ?? '—')}
          </Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>
            Rule: {String(intake.blend?.formula ?? '—')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Flags: {(intake.flags || row.flags || []).join(', ') || 'none'}
          </Typography>
        </Box>
      </Popover>
    </Stack>
  );
}

type CustomerPick = { id: number; customer_code: string; customer_name: string };

export function PromoPlanBuilderPanel() {
  const qc = useQueryClient();
  const lineId = useLineIdentifierPreference();
  const [customer, setCustomer] = useState<CustomerPick | null>(null);
  const [seedCaseId, setSeedCaseId] = useState('');
  const [periodLabel, setPeriodLabel] = useState('2026Q2');
  const [addProductId, setAddProductId] = useState('');
  const [addDistributorId, setAddDistributorId] = useState('');
  const [rows, setRows] = useState<PlannerRow[]>([]);
  const [budgetCheck, setBudgetCheck] = useState<DraftPayload['budget_check']>();
  const [productSetSource, setProductSetSource] = useState<string | null>(null);
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  const [createIsError, setCreateIsError] = useState(false);
  const [draftLoading, setDraftLoading] = useState(false);

  const applyDraft = useCallback((payload: DraftPayload, mode: 'replace' | 'merge') => {
    const incoming = payload.lines ?? [];
    setBudgetCheck(payload.budget_check);
    setProductSetSource((payload as { product_set_source?: string | null }).product_set_source ?? null);
    setRows((prev) => {
      const next = mode === 'merge' ? mergePromoPlanSuggestions(prev, incoming) : hydratePlannerRows(incoming);
      const evidence = new Map(incoming.map((line) => [line.row_key, line.promotion_evidence]));
      return next.map((row) => ({ ...row, evidence_caption: sellthroughCaption(evidence.get(row.row_key)) }));
    });
  }, []);

  const canCompose = Boolean(customer?.id) || /^\d+$/.test(seedCaseId);

  const loadDraft = useCallback(
    async (mode: 'replace' | 'merge', extra?: PlannerRow[]) => {
      if (!canCompose) return;
      setDraftLoading(true);
      try {
        const working = extra ?? rows;
        const period = periodLabel.trim() || null;
        let payload: DraftPayload;
        const body: Record<string, unknown> = {
          period_label: period,
        };
        if (/^\d+$/.test(seedCaseId)) body.seed_case_id = Number(seedCaseId);
        if (customer?.id) body.customer_id = customer.id;
        if (mode === 'merge' || (extra && extra.length)) {
          payload = await apiPost<DraftPayload>('/api/v1/cpor/intelligence/promo-plan-draft/recompute', {
            ...body,
            lines: toRecomputeSpecs(working),
          });
        } else {
          const sp = new URLSearchParams();
          if (typeof body.seed_case_id === 'number') sp.set('seed_case_id', String(body.seed_case_id));
          if (typeof body.customer_id === 'number') sp.set('customer_id', String(body.customer_id));
          if (period) sp.set('period_label', period);
          payload = await apiGet<DraftPayload>(`/api/v1/cpor/intelligence/promo-plan-draft?${sp.toString()}`);
        }
        applyDraft(payload, mode);
      } finally {
        setDraftLoading(false);
      }
    },
    [applyDraft, canCompose, customer, periodLabel, rows, seedCaseId],
  );

  const createFromDraft = useMutation({
    mutationFn: () =>
      apiPost<Record<string, unknown>>('/api/v1/cpor/intelligence/promo-plan-draft/create-case', {
        ...( /^\d+$/.test(seedCaseId) ? { seed_case_id: Number(seedCaseId) } : {}),
        ...(customer?.id ? { customer_id: customer.id } : {}),
        period_label: periodLabel.trim() || null,
        confirm_over_budget: true,
        lines: toCreateLines(rows),
      }),
    onSuccess: (res) => {
      // A new draft case: refresh the case lists, the exact counts and the clash summary.
      void invalidateAfterCaseWrite(qc);
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
      ...lineId.columns<PlannerRow>(
        { sku: 'product_sku', salesModel: 'product_sales_model_name' },
        { minWidth: 120, editable: false },
      ),
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
        valueFormatter: (p) => (
          p.data?.flags.includes('cip_qty_unavailable') && !p.data.dirty_fields.includes('estimate_qty')
            ? 'Not available yet'
            : String(p.value ?? 'Not available yet')
        ),
        cellClassRules: { 'cip-cell-dirty': (p) => Boolean(p.data?.dirty_fields.includes('estimate_qty')) },
      },
      {
        field: 'cost_basis',
        headerName: 'MAC',
        minWidth: 110,
        editable: true,
        cellClassRules: { 'cip-cell-dirty': (p) => Boolean(p.data?.dirty_fields.includes('cost_basis')) },
        valueFormatter: (p) => (p.value == null || p.value === '' ? 'Not available yet' : String(p.value)),
      },
      {
        colId: 'mac_explain',
        headerName: 'Cost evidence',
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
        valueFormatter: (p) => (p.value == null ? 'Not available yet' : String(p.value)),
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
        field: 'evidence_caption',
        headerName: 'Evidence',
        minWidth: 320,
        width: 460,
        editable: false,
        pinned: 'right',
        tooltipValueGetter: (p) => (p.value == null || p.value === '' ? '' : String(p.value)),
      },
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
    [lineId],
  );

  return (
    <Box
      data-testid="promo-plan-builder-b4"
      sx={{
        '& .cip-cell-dirty': { backgroundColor: 'warning.light' },
      }}
    >
      <Typography variant="subtitle1" sx={{ mb: 1 }}>
        Create promotion plan
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Pick a customer and period. Lines are the products that customer’s own sell-through reports. Price,
        cost, stock and expected units all come from that sell-through and nothing else; a figure it does not
        carry shows as not available yet. The Evidence column shows customer cover, and the suggested quantity
        comes from the sell-through run rate and the cover target. Flags do not block.
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
        <Box sx={{ minWidth: 280, flex: 1 }}>
          <EntitySearchAutocomplete<CustomerPick>
            label="Customer"
            value={customer}
            onChange={setCustomer}
            getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
            fetchOptions={async (query, signal) => {
              const needle = query.trim();
              const res = await apiGet<{ items: CustomerPick[] }>(
                `/api/v1/customers?page=1&page_size=25${needle ? `&q=${encodeURIComponent(needle)}` : ''}`,
                { signal },
              );
              return res.items ?? [];
            }}
          />
        </Box>
        <TextField
          size="small"
          label="Period"
          value={periodLabel}
          onChange={(e) => setPeriodLabel(e.target.value)}
          inputProps={{ 'data-testid': 'b4-period-label' }}
          sx={{ width: 140 }}
        />
        <TextField
          size="small"
          label="Seed case id (optional)"
          value={seedCaseId}
          onChange={(e) => setSeedCaseId(e.target.value)}
          inputProps={{ 'data-testid': 'b4-seed-case-id' }}
          sx={{ width: 180 }}
        />
        <Button
          size="small"
          data-testid="b4-build-draft"
          onClick={() => void loadDraft('replace')}
          disabled={!canCompose || draftLoading || !periodLabel.trim()}
        >
          {draftLoading ? 'Building…' : 'Propose from evidence'}
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
          disabled={rows.length === 0 || createFromDraft.isPending || !canCompose}
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
          Open Case book
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
              product_sales_model_name: null,
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
              evidence_caption: sellthroughCaption(undefined),
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
          Over-budget vs entered planned support (warn only unless hard enforce blocks create).
        </Alert>
      ) : null}
      {rows.length > 0 ? (
        <>
          <Typography variant="body2" component="div" data-testid="b4-draft-summary" sx={{ mb: 1 }}>
            Lines: {rows.length} · source: {productSetSource ?? '—'} · budget status{' '}
            {String(budgetCheck?.tracks?.money?.status ?? '—')} · planned reservation USD{' '}
            {budgetCheck?.tracks?.money?.planned_reservation_usd == null
              ? 'Not available yet (it needs line-up units and SKU assumptions, not sell-through)'
              : String(budgetCheck.tracks.money.planned_reservation_usd)}{' '}
            ·{' '}
            {budgetCheck?.drawn_source === 'budget_ledger' ? 'ledger drawn' : 'drawn'} USD{' '}
            {String(budgetCheck?.tracks?.money?.drawn_cpor_usd ?? 0)} · dirty cells survive Refresh
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
            suggested values. The cost evidence is explain-only.
          </Typography>
        </>
      ) : (
        <Typography variant="caption" color="text.secondary">
          Pick a customer and period, then propose from evidence. The customer’s own sell-through is the
          product set. Optional seed case id still works. Edits stick
          across Refresh; Reset restores the suggestion.
        </Typography>
      )}
    </Box>
  );
}
