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
  FormControlLabel,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useRef, useState } from 'react';

import { CporComparableCasesPanel } from '@/app/(app)/commercial-planner/cpor-cases/[id]/CporComparableCasesPanel';
import { CporPaymentEvidencePanel } from '@/app/(app)/commercial-planner/cpor-cases/[id]/CporPaymentEvidencePanel';
import { CporPromoLoadPanel } from '@/app/(app)/commercial-planner/cpor-cases/[id]/CporPromoLoadPanel';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { PageHeader } from '@/components/PageHeader';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { CporFxAnchorPanel } from '@/features/cpor/CporFxAnchorPanel';
import { CporSettleReadinessRow } from '@/features/cpor/CporSettleReadinessRow';
import {
  formatGridMoney,
  formatLocalMoney,
  formatUsdMoney,
  type SettleReadiness,
} from '@/features/cpor/fxDisplay';
import { SettlementConfirmDialog } from '@/features/settlement/SettlementConfirmDialog';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { apiGet, apiPatch, apiPost, apiPostFormData } from '@/lib/api';

type LineRow = {
  id: number;
  product_id: number;
  product_sku: string | null;
  product_name: string | null;
  product_line: string | null;
  distributor_id: number | null;
  pod_quarter: string | null;
  srp: number;
  vat_rate: number;
  dealer_margin_pct: number;
  margin_source: string;
  cost_basis: number | null;
  cost_source: string | null;
  estimate_qty: number;
  dealer_price: number | null;
  support_unit: number | null;
  ttl_support: number | null;
  support_usd: number | null;
  flags: string[];
};

export type CaseDetail = {
  id: number;
  case_code: string;
  customer_code: string | null;
  customer_name: string | null;
  promotion_type: string;
  window_start: string | null;
  window_end: string | null;
  status: string;
  workflow_status: string;
  export_version: number;
  currency_code?: string;
  roe_snapshot: number | null;
  fx_mode?: string | null;
  last_comment: string | null;
  allowed_next: string[];
  lines: LineRow[];
  flags: string[];
  missing_roe: boolean;
  ttl_support_zar: number | null;
  ttl_support_usd: number | null;
  outstanding_amount?: number | null;
  settle_readiness?: SettleReadiness;
  needs_reapproval?: boolean;
};

type Pivot = {
  cells: Record<string, Record<string, number>>;
  row_totals: Record<string, number>;
  col_totals: Record<string, number>;
  grand_total_usd: number;
  missing_roe: boolean;
};

type ProductPick = { id: number; sku: string; name: string };

type SettlementLine = {
  line_id: number;
  product_id: number | null;
  estimate_qty: number;
  result_qty: number | null;
  support_unit: number | null;
  ttl_support: number | null;
  ttl_result: number | null;
  ttl_support_usd: number | null;
  ttl_result_usd: number | null;
  flags: string[];
};

export type SettlementPayload = {
  case_id: number;
  status: string;
  window_start: string | null;
  window_end: string | null;
  claim_row_count: number;
  out_of_window_claim_rows: number;
  unresolved_products: { token: string; units: number }[];
  cst_reconciliation: {
    available: boolean;
    reason?: string;
    divergence_count?: number;
    products_compared?: number;
  };
  settle_readiness?: SettleReadiness;
  lines: SettlementLine[];
  can_settle: boolean;
};

const ACTION_LABELS: Record<string, string> = {
  propose: 'Propose',
  approve: 'Approve',
  reject: 'Reject',
  resend: 'Resend',
  activate: 'Activate',
  end: 'End',
  settle: 'Settle',
  cancel: 'Cancel',
};

type CporCaseWorkspaceProps = {
  caseId: number;
  embedded?: boolean;
  defaultTab?: number;
};

export function CporCaseWorkspace({ caseId, embedded = false, defaultTab = 0 }: CporCaseWorkspaceProps) {
  const qc = useQueryClient();
  const [tab, setTab] = useState(defaultTab);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectComment, setRejectComment] = useState('');
  const [settleConfirmOpen, setSettleConfirmOpen] = useState(false);
  const [lineOpen, setLineOpen] = useState(false);
  const [product, setProduct] = useState<ProductPick | null>(null);
  const [srp, setSrp] = useState('13999');
  const [vat, setVat] = useState('0.15');
  const [estimate, setEstimate] = useState('20');
  const [podQuarter, setPodQuarter] = useState('');
  const [costOverride, setCostOverride] = useState('');
  const [includeOow, setIncludeOow] = useState(false);
  const claimFileRef = useRef<HTMLInputElement | null>(null);

  const linesGridHeight = embedded ? 360 : 480;
  const settlementGridHeight = embedded ? 280 : 360;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['cpor', 'case', caseId],
    queryFn: ({ signal }) => apiGet<CaseDetail>(`/api/v1/cpor/cases/${caseId}`, { signal }),
    enabled: caseId > 0,
  });

  const { data: pivot } = useQuery({
    queryKey: ['cpor', 'pivot', caseId],
    queryFn: ({ signal }) => apiGet<Pivot>(`/api/v1/cpor/cases/${caseId}/pivot`, { signal }),
    enabled: caseId > 0 && tab === 1,
  });

  const { data: events } = useQuery({
    queryKey: ['cpor', 'events', caseId],
    queryFn: ({ signal }) =>
      apiGet<{ id: number; event_type: string; actor: string | null; created_at: string | null }[]>(
        `/api/v1/cpor/cases/${caseId}/events`,
        { signal },
      ),
    enabled: caseId > 0 && tab === 2,
  });

  const { data: exports, refetch: refetchExports } = useQuery({
    queryKey: ['cpor', 'exports', caseId],
    queryFn: ({ signal }) =>
      apiGet<{
        exports: {
          export_version: number;
          file_name: string | null;
          checksum_sha256: string | null;
          actor: string | null;
          created_at: string | null;
          is_latest_for_version: boolean;
          flags_present: string[];
        }[];
      }>(`/api/v1/cpor/cases/${caseId}/exports`, { signal }),
    enabled: caseId > 0 && tab === 3,
  });

  const {
    data: settlement,
    refetch: refetchSettlement,
    isFetching: settlementLoading,
  } = useQuery({
    queryKey: ['cpor', 'settlement', caseId],
    queryFn: ({ signal }) => apiGet<SettlementPayload>(`/api/v1/cpor/cases/${caseId}/settlement`, { signal }),
    enabled: caseId > 0 && tab === 4,
  });

  const generateExport = useMutation({
    mutationFn: () => apiPost(`/api/v1/cpor/cases/${caseId}/export`, {}),
    onSuccess: async () => {
      await refetchExports();
    },
  });

  const transition = useMutation({
    mutationFn: (payload: { action: string; comment?: string; confirm_over_budget_reapproval?: boolean }) =>
      apiPost(`/api/v1/cpor/cases/${caseId}/transition`, payload),
    onSuccess: async (_result, variables) => {
      setRejectOpen(false);
      setSettleConfirmOpen(false);
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      if (variables.action === 'settle') {
        await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', 'book'] });
        await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
      }
      await refetch();
    },
  });

  const addLine = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/cpor/cases/${caseId}/lines`, {
        product_id: product!.id,
        srp: Number(srp),
        vat_rate: Number(vat),
        estimate_qty: Number(estimate),
        pod_quarter: podQuarter.trim() || null,
        cost_basis: costOverride.trim() ? Number(costOverride) : null,
        cost_source: costOverride.trim() ? 'manual' : null,
        accept_cost_suggestion: !costOverride.trim(),
      }),
    onSuccess: async () => {
      setLineOpen(false);
      setProduct(null);
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await refetch();
    },
  });

  const importClaims = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('include_out_of_window', includeOow ? 'true' : 'false');
      return apiPostFormData<{
        import: { rows_upserted: number; unresolved_product_rows: number; out_of_window_rows: number };
        rollup: { lines_updated: number };
        settlement: SettlementPayload;
      }>(`/api/v1/cpor/cases/${caseId}/claim-evidence/import`, fd);
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', caseId] });
      await refetch();
      await refetchSettlement();
    },
  });

  const rollupSettlement = useMutation({
    mutationFn: () => apiPost(`/api/v1/cpor/cases/${caseId}/settlement/rollup`, {}),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', caseId] });
      await refetch();
      await refetchSettlement();
    },
  });

  const patchFxMode = useMutation({
    mutationFn: (fx_mode: 'booked' | 'floating') => apiPatch(`/api/v1/cpor/cases/${caseId}`, { fx_mode }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await refetch();
    },
  });

  const lineCols = useMemo<ColDef<LineRow>[]>(
    () => [
      { field: 'product_sku', headerName: 'SKU', width: 120 },
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 160 },
      { field: 'pod_quarter', headerName: 'POD Q', width: 90 },
      { field: 'srp', headerName: 'SRP', width: 100 },
      { field: 'dealer_margin_pct', headerName: 'Margin', width: 90 },
      { field: 'cost_basis', headerName: 'Cost', width: 100 },
      { field: 'cost_source', headerName: 'Cost src', width: 120 },
      {
        field: 'dealer_price',
        headerName: 'Dealer px',
        width: 110,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        field: 'support_unit',
        headerName: 'Support/u',
        width: 100,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        field: 'ttl_support',
        headerName: 'Ttl (local)',
        width: 120,
        valueFormatter: (p) =>
          formatLocalMoney(p.value as number | null, data?.currency_code ?? 'ZAR'),
      },
      {
        headerName: 'Flags',
        width: 160,
        valueGetter: (p) => (p.data?.flags ?? []).join(', '),
      },
    ],
    [data?.currency_code],
  );

  const settlementCols = useMemo<ColDef<SettlementLine>[]>(
    () => [
      { field: 'product_id', headerName: 'Product', width: 100 },
      { field: 'estimate_qty', headerName: 'Estimate', width: 100 },
      { field: 'result_qty', headerName: 'Result', width: 100 },
      {
        field: 'support_unit',
        headerName: 'Support/u',
        width: 110,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        field: 'ttl_result',
        headerName: 'Ttl result (local)',
        width: 140,
        valueFormatter: (p) =>
          formatLocalMoney(p.value as number | null, data?.currency_code ?? 'ZAR'),
      },
      {
        field: 'ttl_result_usd',
        headerName: 'Ttl result USD',
        width: 140,
        valueFormatter: (p) =>
          formatGridMoney(p.value as number | null, 'usd', {
            currencyCode: data?.currency_code,
            roeSnapshot: data?.roe_snapshot,
            missingRoe: data?.missing_roe,
          }),
      },
      {
        headerName: 'Flags',
        flex: 1,
        minWidth: 160,
        valueGetter: (p) => (p.data?.flags ?? []).join(', '),
      },
    ],
    [data?.currency_code, data?.missing_roe, data?.roe_snapshot],
  );

  if (isLoading) return <Typography sx={{ p: 2 }}>Loading…</Typography>;
  if (isError || !data) {
    return <Alert severity="error">{String((error as Error)?.message ?? 'Failed to load case')}</Alert>;
  }

  const actions = Object.entries(ACTION_LABELS).filter(([action]) => {
    const map: Record<string, string> = {
      propose: 'proposed',
      approve: 'approved',
      reject: 'rejected',
      resend: 'proposed',
      activate: 'active',
      end: 'ended',
      settle: 'settled',
      cancel: 'cancelled',
    };
    if (action === 'resend') return data.status === 'rejected';
    if (action === 'settle' && data.settle_readiness?.fx_settle_allowed === false) return false;
    const target = map[action];
    return target ? data.allowed_next.includes(target) : false;
  });

  const settleReadiness = settlement?.settle_readiness ?? data.settle_readiness;
  const customerLabel = [data.customer_code, data.customer_name].filter(Boolean).join(' — ');
  const periodLabel =
    data.window_start || data.window_end ? `${data.window_start ?? '…'} → ${data.window_end ?? '…'}` : undefined;

  const workspace = (
    <>
      {!embedded ? (
        <PageHeader
          {...navPageChrome(`/commercial-planner/cpor-cases/${data.id}`, {
            extraCrumbs: [{ label: data.case_code }],
            title: data.case_code,
          })}
        />
      ) : null}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap">
        <Chip label={data.status} color="primary" size="small" />
        <Chip label={`workflow: ${data.workflow_status}`} size="small" />
        <Chip label={`v${data.export_version}`} size="small" />
        {data.needs_reapproval ? (
          <Chip label="needs reapproval (over budget)" color="error" size="small" data-testid="cpor-needs-reapproval" />
        ) : null}
        {data.missing_roe ? <Chip label="missing_roe" color="warning" size="small" /> : null}
        {(data.flags ?? []).slice(0, 6).map((f) => (
          <Chip key={f} label={f} size="small" variant="outlined" />
        ))}
      </Stack>
      {data.settle_readiness ? (
        <Box sx={{ mb: 1.5 }}>
          <CporSettleReadinessRow readiness={data.settle_readiness} testIdPrefix="cpor-case-readiness" />
          {data.settle_readiness.fx_basis_line ? (
            <Typography
              variant="caption"
              color="text.secondary"
              data-testid="cpor-fx-basis-line"
              sx={{ display: 'block', mt: 0.5 }}
            >
              {data.settle_readiness.fx_basis_line}
            </Typography>
          ) : null}
        </Box>
      ) : null}
      {!data.missing_roe ? (
        <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} flexWrap="wrap" useFlexGap>
          <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center' }}>
            FX mode:
          </Typography>
          {(['booked', 'floating'] as const).map((mode) => (
            <Button
              key={mode}
              size="small"
              variant={data.fx_mode === mode ? 'contained' : 'outlined'}
              disabled={patchFxMode.isPending}
              onClick={() => patchFxMode.mutate(mode)}
              data-testid={`cpor-fx-mode-${mode}`}
            >
              {mode}
            </Button>
          ))}
        </Stack>
      ) : null}
      {data.needs_reapproval ? (
        <Alert severity="warning" sx={{ mb: 1 }} data-testid="cpor-reapproval-banner">
          Money ceiling exceeded or reapproval required. Approve with over-budget confirmation, or reduce
          support / raise the tenant money ceiling.
        </Alert>
      ) : null}
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {data.customer_code} — {data.customer_name} · {data.promotion_type} · {data.window_start} →{' '}
        {data.window_end}
        {data.currency_code ? ` · ${data.currency_code}` : ''}
        {data.last_comment ? ` · PM: ${data.last_comment}` : ''}
      </Typography>
      <CporFxAnchorPanel
        currencyCode={data.currency_code}
        roeSnapshot={data.roe_snapshot}
        missingRoe={data.missing_roe}
        localAmount={data.ttl_support_zar}
        usdAmount={data.ttl_support_usd}
        localLabel="Approved case support"
      />
      <CporComparableCasesPanel caseId={caseId} />
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap">
        {actions.map(([action, label]) => (
          <Button
            key={action}
            size="small"
            variant={action === 'reject' || action === 'cancel' ? 'outlined' : 'contained'}
            color={action === 'reject' || action === 'cancel' ? 'warning' : 'primary'}
            disabled={transition.isPending}
            onClick={() => {
              if (action === 'reject') setRejectOpen(true);
              else if (action === 'settle') setSettleConfirmOpen(true);
              else if (action === 'approve' && data.needs_reapproval) {
                transition.mutate({ action: 'approve', confirm_over_budget_reapproval: true });
              } else transition.mutate({ action });
            }}
            data-testid={`cpor-action-${action}`}
          >
            {action === 'approve' && data.needs_reapproval ? 'Reapprove (over budget)' : label}
          </Button>
        ))}
        <Box sx={{ flex: 1 }} />
        <Button size="small" variant="outlined" onClick={() => setLineOpen(true)}>
          Add line
        </Button>
      </Stack>
      {transition.isError ? (
        <Alert severity="error" sx={{ mb: 1 }}>
          {String((transition.error as Error)?.message)}
        </Alert>
      ) : null}

      <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 1 }}>
        <Tab label="Lines" />
        <Tab label="USD pivot" />
        <Tab label="Events" />
        <Tab label="Exports" />
        <Tab label="Settlement" data-testid="cpor-tab-settlement" />
        <Tab label="Promo load" data-testid="cpor-tab-promo-load" />
        <Tab label="Payments / recon" data-testid="cpor-tab-payments" />
      </Tabs>

      {tab === 0 ? (
        <EnterpriseDataGrid
          rowData={data.lines ?? []}
          columnDefs={lineCols}
          height={linesGridHeight}
          gridOptions={{ getRowId: (p) => String(p.data.id) }}
        />
      ) : null}

      {tab === 1 ? (
        <Box>
          {pivot?.missing_roe ? (
            <Alert severity="warning" data-testid="cpor-pivot-missing-roe">
              FX undeclared — USD pivot totals are withheld until a case rate of exchange is recorded.
            </Alert>
          ) : null}
          {pivot && !pivot.missing_roe ? (
            <Typography variant="subtitle2" sx={{ mt: 1 }} data-testid="cpor-pivot-grand-total">
              Grand total USD: {formatUsdMoney(pivot.grand_total_usd)}
              {data.roe_snapshot != null ? (
                <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                  at declared case rate ZAR {data.roe_snapshot.toFixed(2)} (declared case terms)
                </Typography>
              ) : null}
            </Typography>
          ) : null}
          <pre style={{ fontSize: 12, overflow: 'auto' }}>{JSON.stringify(pivot?.cells ?? {}, null, 2)}</pre>
        </Box>
      ) : null}

      {tab === 2 ? (
        <Stack spacing={0.5}>
          {(events ?? []).map((e) => (
            <Typography key={e.id} variant="body2">
              {e.created_at} · <strong>{e.event_type}</strong> · {e.actor ?? '—'}
            </Typography>
          ))}
        </Stack>
      ) : null}

      {tab === 3 ? (
        <Stack spacing={1.5}>
          <Button
            variant="contained"
            size="small"
            disabled={generateExport.isPending}
            onClick={() => generateExport.mutate()}
            data-testid="cpor-generate-export"
            sx={{ alignSelf: 'flex-start' }}
          >
            {generateExport.isPending ? 'Generating…' : 'Generate export'}
          </Button>
          {generateExport.isError ? (
            <Alert severity="error">{String((generateExport.error as Error)?.message)}</Alert>
          ) : null}
          {(exports?.exports ?? []).length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No exports yet.
            </Typography>
          ) : (
            (exports?.exports ?? []).map((ex, i) => (
              <Stack key={`${ex.export_version}-${i}`} direction="row" spacing={1} alignItems="center">
                <Typography variant="body2">
                  v{ex.export_version} · {ex.created_at} · {ex.actor ?? '—'} · {ex.file_name}
                  {ex.is_latest_for_version ? ' (latest)' : ''}
                </Typography>
                {(ex.flags_present ?? []).map((f) => (
                  <Chip key={f} size="small" label={f} variant="outlined" />
                ))}
                <Button
                  size="small"
                  href={`/api/v1/cpor/cases/${caseId}/exports/${ex.export_version}/file`}
                  target="_blank"
                >
                  Download
                </Button>
              </Stack>
            ))
          )}
        </Stack>
      ) : null}

      {tab === 4 ? (
        <Stack spacing={1.5} data-testid="cpor-settlement-panel">
          <Alert severity="info">
            Claim evidence is the settlement source of record. Over-estimate and CST divergence are flags only —
            they never block settle. Unresolved products stay on the worklist and do not block other claim rows.
          </Alert>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Button
              size="small"
              variant="contained"
              disabled={importClaims.isPending}
              onClick={() => claimFileRef.current?.click()}
              data-testid="cpor-claim-upload"
            >
              {importClaims.isPending ? 'Importing…' : 'Upload claim evidence'}
            </Button>
            <input
              ref={claimFileRef}
              type="file"
              accept=".csv,.xlsx"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = '';
                if (f) importClaims.mutate(f);
              }}
            />
            <FormControlLabel
              control={
                <Checkbox
                  size="small"
                  checked={includeOow}
                  onChange={(e) => setIncludeOow(e.target.checked)}
                />
              }
              label="Include out-of-window rows in rollup"
            />
            <Button
              size="small"
              variant="outlined"
              disabled={rollupSettlement.isPending || settlementLoading}
              onClick={() => rollupSettlement.mutate()}
              data-testid="cpor-settlement-rollup"
            >
              Re-rollup from claims
            </Button>
            {settlement?.can_settle ? (
              <Button
                size="small"
                variant="contained"
                color="success"
                disabled={transition.isPending}
                onClick={() => setSettleConfirmOpen(true)}
                data-testid="cpor-settle-from-panel"
              >
                Settle case
              </Button>
            ) : null}
          </Stack>
          {importClaims.isError ? (
            <Alert severity="error">{String((importClaims.error as Error)?.message)}</Alert>
          ) : null}
          {rollupSettlement.isError ? (
            <Alert severity="error">{String((rollupSettlement.error as Error)?.message)}</Alert>
          ) : null}
          {importClaims.isSuccess ? (
            <Alert severity="success">
              Upserted {importClaims.data.import.rows_upserted} claim row(s); updated{' '}
              {importClaims.data.rollup.lines_updated} line(s). Unresolved:{' '}
              {importClaims.data.import.unresolved_product_rows}; out-of-window:{' '}
              {importClaims.data.import.out_of_window_rows}.
            </Alert>
          ) : null}
          {settleReadiness ? (
            <CporSettleReadinessRow readiness={settleReadiness} testIdPrefix="cpor-settlement-readiness" />
          ) : null}
          <Stack direction="row" spacing={1} flexWrap="wrap">
            <Chip size="small" label={`claims: ${settlement?.claim_row_count ?? '…'}`} />
            <Chip size="small" label={`out-of-window: ${settlement?.out_of_window_claim_rows ?? '…'}`} />
            <Chip
              size="small"
              color={(settlement?.unresolved_products?.length ?? 0) > 0 ? 'warning' : 'default'}
              label={`unresolved products: ${settlement?.unresolved_products?.length ?? '…'}`}
            />
            <Chip
              size="small"
              color={
                settlement?.cst_reconciliation?.available &&
                (settlement.cst_reconciliation.divergence_count ?? 0) > 0
                  ? 'warning'
                  : 'default'
              }
              label={
                settlement?.cst_reconciliation?.available
                  ? `CST divergence: ${settlement.cst_reconciliation.divergence_count ?? 0}`
                  : `CST: ${settlement?.cst_reconciliation?.reason ?? 'n/a'}`
              }
            />
          </Stack>
          {(settlement?.unresolved_products ?? []).length > 0 ? (
            <Typography variant="body2" color="text.secondary">
              Unresolved tokens:{' '}
              {settlement!.unresolved_products.map((u) => `${u.token} (${u.units})`).join(', ')}
            </Typography>
          ) : null}
          <EnterpriseDataGrid
            rowData={settlement?.lines ?? []}
            columnDefs={settlementCols}
            height={settlementGridHeight}
            gridOptions={{ getRowId: (p) => String(p.data.line_id) }}
          />
        </Stack>
      ) : null}

      {tab === 5 ? <CporPromoLoadPanel caseId={caseId} /> : null}
      {tab === 6 ? <CporPaymentEvidencePanel caseId={caseId} /> : null}

      <SettlementConfirmDialog
        open={settleConfirmOpen}
        onClose={() => setSettleConfirmOpen(false)}
        onConfirm={() => transition.mutate({ action: 'settle' })}
        confirming={transition.isPending}
        caseCode={data.case_code}
        customerLabel={customerLabel}
        periodLabel={periodLabel}
        outstandingAmount={data.outstanding_amount ?? data.ttl_support_zar}
        currencyCode={data.currency_code}
        settleReadiness={settleReadiness}
        claimRowCount={settlement?.claim_row_count ?? data.settle_readiness?.claim_evidence_count ?? 0}
        unresolvedProductCount={settlement?.unresolved_products?.length ?? 0}
      />

      <Dialog open={rejectOpen} onClose={() => setRejectOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Reject case</DialogTitle>
        <DialogContent>
          <TextField
            label="PM feedback (required)"
            value={rejectComment}
            onChange={(e) => setRejectComment(e.target.value)}
            fullWidth
            multiline
            minRows={3}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejectOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!rejectComment.trim() || transition.isPending}
            onClick={() => transition.mutate({ action: 'reject', comment: rejectComment })}
          >
            Reject
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={lineOpen} onClose={() => !addLine.isPending && setLineOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add line</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <EntitySearchAutocomplete<ProductPick>
              label="Product"
              value={product}
              onChange={setProduct}
              getOptionLabel={(o) => `${o.sku} — ${o.name}`}
              fetchOptions={async (q, signal) => {
                const res = await apiGet<{ items: ProductPick[] }>(
                  `/api/v1/products?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                  { signal },
                );
                return res.items ?? [];
              }}
            />
            <TextField size="small" label="SRP" value={srp} onChange={(e) => setSrp(e.target.value)} />
            <TextField size="small" label="VAT rate" value={vat} onChange={(e) => setVat(e.target.value)} />
            <TextField
              size="small"
              label="Estimate qty"
              value={estimate}
              onChange={(e) => setEstimate(e.target.value)}
            />
            <TextField
              size="small"
              label="POD quarter (optional layer)"
              value={podQuarter}
              onChange={(e) => setPodQuarter(e.target.value)}
            />
            <TextField
              size="small"
              label="Manual cost override (optional)"
              value={costOverride}
              onChange={(e) => setCostOverride(e.target.value)}
              helperText="Leave blank to accept CST/sell-out suggestion"
            />
            {addLine.isError ? <Alert severity="error">{String((addLine.error as Error)?.message)}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLineOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!product || addLine.isPending} onClick={() => addLine.mutate()}>
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );

  if (embedded) {
    return <Box data-testid="cpor-case-workspace-embedded">{workspace}</Box>;
  }

  return workspace;
}
