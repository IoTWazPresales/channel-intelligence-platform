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
import { useParams } from 'next/navigation';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { PageHeader } from '@/components/PageHeader';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { apiGet, apiPost, apiPostFormData } from '@/lib/api';

import { CporComparableCasesPanel } from './CporComparableCasesPanel';

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

type CaseDetail = {
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
  roe_snapshot: number | null;
  last_comment: string | null;
  allowed_next: string[];
  lines: LineRow[];
  flags: string[];
  missing_roe: boolean;
  ttl_support_zar: number | null;
  ttl_support_usd: number | null;
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

type SettlementPayload = {
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

export default function CporCaseDetailPage() {
  const params = useParams<{ id: string }>();
  const caseId = Number(params.id);
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectComment, setRejectComment] = useState('');
  const [lineOpen, setLineOpen] = useState(false);
  const [product, setProduct] = useState<ProductPick | null>(null);
  const [srp, setSrp] = useState('13999');
  const [vat, setVat] = useState('0.15');
  const [estimate, setEstimate] = useState('20');
  const [podQuarter, setPodQuarter] = useState('');
  const [costOverride, setCostOverride] = useState('');
  const [includeOow, setIncludeOow] = useState(false);
  const claimFileRef = useRef<HTMLInputElement | null>(null);

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
    mutationFn: (payload: { action: string; comment?: string }) =>
      apiPost(`/api/v1/cpor/cases/${caseId}/transition`, payload),
    onSuccess: async () => {
      setRejectOpen(false);
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
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
        headerName: 'Ttl ZAR',
        width: 100,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        headerName: 'Flags',
        width: 160,
        valueGetter: (p) => (p.data?.flags ?? []).join(', '),
      },
    ],
    [],
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
        headerName: 'Ttl result ZAR',
        width: 130,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        field: 'ttl_result_usd',
        headerName: 'Ttl result USD',
        width: 130,
        valueFormatter: (p) => (p.value == null ? '' : Number(p.value).toFixed(2)),
      },
      {
        headerName: 'Flags',
        flex: 1,
        minWidth: 160,
        valueGetter: (p) => (p.data?.flags ?? []).join(', '),
      },
    ],
    [],
  );

  if (isLoading) return <Typography sx={{ p: 2 }}>Loading…</Typography>;
  if (isError || !data) {
    return <Alert severity="error">{String((error as Error)?.message ?? 'Failed to load case')}</Alert>;
  }

  const actions = Object.entries(ACTION_LABELS).filter(([action]) => {
    // enable based on allowed_next via known mapping
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
    const target = map[action];
    return target ? data.allowed_next.includes(target) : false;
  });

  return (
    <>
      <PageHeader
        crumbs={[
          { label: 'Commercial Planning' },
          { label: 'CPOR Cases', href: '/commercial-planner/cpor-cases' },
          { label: data.case_code },
        ]}
        title={data.case_code}
      />
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
      {data.needs_reapproval ? (
        <Alert severity="warning" sx={{ mb: 1 }} data-testid="cpor-reapproval-banner">
          Money ceiling exceeded or reapproval required. Approve with over-budget confirmation, or reduce
          support / raise the tenant money ceiling.
        </Alert>
      ) : null}
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {data.customer_code} — {data.customer_name} · {data.promotion_type} · {data.window_start} →{' '}
        {data.window_end}
        {data.roe_snapshot != null ? ` · ROE ${data.roe_snapshot}` : ''}
        {data.last_comment ? ` · PM: ${data.last_comment}` : ''}
      </Typography>
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
      </Tabs>

      {tab === 0 ? (
        <EnterpriseDataGrid
          rowData={data.lines ?? []}
          columnDefs={lineCols}
          height={480}
          gridOptions={{ getRowId: (p) => String(p.data.id) }}
        />
      ) : null}

      {tab === 1 ? (
        <Box>
          {pivot?.missing_roe ? <Alert severity="warning">ROE missing — USD totals may be empty.</Alert> : null}
          <Typography variant="subtitle2" sx={{ mt: 1 }}>
            Grand total USD: {pivot ? pivot.grand_total_usd.toFixed(2) : '…'}
          </Typography>
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
                onClick={() => transition.mutate({ action: 'settle' })}
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
            height={360}
            gridOptions={{ getRowId: (p) => String(p.data.line_id) }}
          />
        </Stack>
      ) : null}

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
}
