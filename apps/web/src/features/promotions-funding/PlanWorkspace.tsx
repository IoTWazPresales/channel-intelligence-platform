'use client';

import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import type { CellClickedEvent, CellValueChangedEvent, ColDef } from 'ag-grid-community';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import NextLink from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';

import { CporComparableCasesPanel } from '@/app/(app)/commercial-planner/cpor-cases/[id]/CporComparableCasesPanel';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { PLANNER_CAPABILITIES } from '@/features/promotions-funding/capabilities';
import { fmtCompact, fmtInt, fmtMoney, fmtPct } from '@/features/promotions-funding/format';
import {
  ACTION_LABELS,
  estimateQtyFromLines,
  LIFECYCLE_STAGES,
  ORIGIN_LABEL,
  STAGE_LABEL,
  stageTone,
  supportFromLines,
  type PlanStage,
} from '@/features/promotions-funding/lifecycle';
import type { CporCaseDetail, CporCaseLine, SupportBiasRead } from '@/features/promotions-funding/types';
import { apiDownloadBlob, apiGet, apiPatch, apiPost } from '@/lib/api';
import { CapabilityLedger } from '@/features/workbench-ui/CapabilityLedger';
import { EntityContextPanel, KeyValueList } from '@/features/workbench-ui/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { LifecycleRail } from '@/features/workbench-ui/LifecycleRail';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { StatusChip } from '@/features/workbench-ui/controls';

type ProductPick = { id: number; sku: string; name: string };

const EDITABLE = new Set(['draft', 'rejected']);

const ACTION_TARGET: Record<string, string> = {
  propose: 'proposed',
  approve: 'approved',
  reject: 'rejected',
  resend: 'proposed',
  activate: 'active',
  end: 'ended',
  settle: 'settled',
  cancel: 'cancelled',
};

export function PlanWorkspace({ caseId, onBack }: { caseId: number; onBack: () => void }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const router = useRouter();
  const qc = useQueryClient();
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectComment, setRejectComment] = useState('');
  const [exportOpen, setExportOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [product, setProduct] = useState<ProductPick | null>(null);
  const [srp, setSrp] = useState('13999');
  const [estimate, setEstimate] = useState('20');

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['cpor', 'case', caseId],
    queryFn: ({ signal }) => apiGet<CporCaseDetail>(`/api/v1/cpor/cases/${caseId}`, { signal }),
    enabled: caseId > 0,
  });

  const { data: bias } = useQuery({
    queryKey: ['cpor', 'support-bias', caseId],
    queryFn: ({ signal }) =>
      apiGet<SupportBiasRead>(`/api/v1/cpor/intelligence/support-bias?case_id=${caseId}`, { signal }),
    enabled: caseId > 0,
  });

  const editable = !!data && EDITABLE.has(data.status);
  const ccy = data?.currency_code ?? 'ZAR';
  const lines = data?.lines ?? [];
  const line = lines.find((l) => l.id === selectedLine) ?? null;
  const support = data ? (data.ttl_support_zar ?? supportFromLines(lines)) : 0;
  const units = estimateQtyFromLines(lines);
  const flagCount = lines.reduce((n, l) => n + (l.flags?.length ?? 0), 0);
  const plannedUsd = bias?.totals?.planned_usd ?? null;
  const drawnUsd = bias?.totals?.actual_usd ?? null;
  const budgetPct =
    plannedUsd && plannedUsd > 0 && drawnUsd != null ? Math.round((drawnUsd / plannedUsd) * 100) : null;
  const overBudget = budgetPct != null && budgetPct > 100;

  const patchLine = useMutation({
    mutationFn: (payload: { lineId: number; body: Record<string, number> }) =>
      apiPatch(`/api/v1/cpor/cases/${caseId}/lines/${payload.lineId}`, payload.body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
    },
    onError: (e) => setToast(e instanceof Error ? e.message : String(e)),
  });

  const transition = useMutation({
    mutationFn: (payload: { action: string; comment?: string }) =>
      apiPost(`/api/v1/cpor/cases/${caseId}/transition`, payload),
    onSuccess: async (_r, vars) => {
      setRejectOpen(false);
      setToast(`${data?.case_code ?? caseId} → ${ACTION_LABELS[vars.action] ?? vars.action}`);
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
      await refetch();
    },
    onError: (e) => setToast(e instanceof Error ? e.message : String(e)),
  });

  const addLine = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/cpor/cases/${caseId}/lines`, {
        product_id: product!.id,
        srp: Number(srp),
        vat_rate: 0.15,
        estimate_qty: Number(estimate),
      }),
    onSuccess: async () => {
      setAddOpen(false);
      setProduct(null);
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await refetch();
    },
    onError: (e) => setToast(e instanceof Error ? e.message : String(e)),
  });

  const exportCase = useMutation({
    mutationFn: async () => {
      const created = await apiPost<{ export_version?: number }>(`/api/v1/cpor/cases/${caseId}/export`, {});
      const version = created?.export_version;
      if (version != null) {
        await apiDownloadBlob(
          `/api/v1/cpor/cases/${caseId}/exports/${version}/file`,
          `${data?.case_code ?? 'cpor'}-v${version}.xlsx`,
        );
      }
      return created;
    },
    onSuccess: () => setToast(`${data?.case_code ?? caseId} export recorded on the case.`),
    onError: (e) => setToast(e instanceof Error ? e.message : String(e)),
  });

  const onCell = (e: CellValueChangedEvent<CporCaseLine>) => {
    if (!e.data || !e.colDef.field) return;
    const field = e.colDef.field;
    if (field !== 'srp' && field !== 'dealer_margin_pct' && field !== 'estimate_qty') return;
    const value = Number(e.newValue);
    if (!Number.isFinite(value)) return;
    patchLine.mutate({ lineId: e.data.id, body: { [field]: value } });
    setToast(`${e.data.product_sku ?? e.data.id}: waterfall recomputed on the server`);
  };

  const columnDefs = useMemo<ColDef<CporCaseLine>[]>(
    () => [
      {
        field: 'product_sku',
        headerName: 'Product',
        minWidth: 210,
        flex: 1.4,
        pinned: 'left',
        cellRenderer: (p: { data?: CporCaseLine }) =>
          p.data ? (
            <Box sx={{ lineHeight: 1.2 }}>
              <Typography variant="body2" noWrap>
                {p.data.product_name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {p.data.product_sku} · layer {p.data.pod_quarter ?? '—'}
              </Typography>
            </Box>
          ) : null,
      },
      {
        field: 'srp',
        headerName: 'Promo SRP',
        type: 'rightAligned',
        width: 115,
        editable,
        valueFormatter: (p) => fmtMoney(p.value as number, ccy),
        cellClass: editable ? 'lab-editable' : undefined,
      },
      {
        field: 'dealer_margin_pct',
        headerName: 'Dealer %',
        type: 'rightAligned',
        width: 95,
        editable,
        valueFormatter: (p) => fmtPct(p.value as number),
        valueParser: (p) => {
          const n = Number(String(p.newValue).replace('%', ''));
          return n > 1 ? n / 100 : n;
        },
      },
      {
        field: 'dealer_price',
        headerName: 'Dealer price',
        type: 'rightAligned',
        width: 115,
        valueFormatter: (p) => fmtMoney(p.value as number | null, ccy),
      },
      {
        field: 'cost_basis',
        headerName: 'Cost basis',
        type: 'rightAligned',
        width: 115,
        valueFormatter: (p) => fmtMoney(p.value as number | null, ccy),
      },
      {
        field: 'support_unit',
        headerName: 'Support / unit',
        type: 'rightAligned',
        width: 120,
        valueFormatter: (p) => fmtMoney(p.value as number | null, ccy),
      },
      {
        field: 'estimate_qty',
        headerName: 'Est. units',
        type: 'rightAligned',
        width: 105,
        editable,
        valueFormatter: (p) => fmtInt(p.value as number),
        cellClass: editable ? 'lab-editable' : undefined,
      },
      {
        field: 'ttl_support',
        headerName: 'Line support',
        type: 'rightAligned',
        width: 125,
        valueFormatter: (p) => fmtCompact(p.value as number | null, ccy),
      },
      {
        field: 'flags',
        headerName: 'Flags',
        minWidth: 220,
        flex: 1.4,
        valueFormatter: (p) => ((p.value as string[]) ?? []).join(' · '),
        cellStyle: (p) => (((p.value as string[]) ?? []).length ? { color: theme.palette.warning.main } : null),
      },
    ],
    [ccy, editable, theme],
  );

  if (isLoading) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        Loading plan…
      </Typography>
    );
  }
  if (isError || !data) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        {(error as Error)?.message ?? 'Case not found'}
      </Alert>
    );
  }

  const stage = data.status as PlanStage;
  const nextActions: [string, string][] = Object.entries(ACTION_LABELS).filter(([action]) => {
    if (action === 'resend') return data.status === 'rejected';
    return (data.allowed_next ?? []).includes(ACTION_TARGET[action]);
  });

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="plan-workspace">
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'flex-end' }} spacing={1}>
        <Box sx={{ minWidth: 0 }}>
          <Button size="small" onClick={onBack} sx={{ ml: -1, mb: 0.25 }}>
            ‹ All plans
          </Button>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="h6" sx={{ fontWeight: 650, lineHeight: 1.2 }}>
              {data.case_name || data.case_code}
            </Typography>
            <StatusChip label={STAGE_LABEL[stage] ?? data.status} tone={stageTone(data.status)} />
            <Typography variant="caption" color="text.secondary">
              {data.case_code} · {data.customer_name} · {ORIGIN_LABEL[data.origin ?? 'native'] ?? data.origin}
            </Typography>
          </Stack>
        </Box>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button
            size="small"
            variant="outlined"
            startIcon={<FileDownloadOutlinedIcon />}
            onClick={() => setExportOpen(true)}
            disabled={exportCase.isPending}
            data-testid="plan-export"
          >
            Export
          </Button>
          {nextActions.map(([action, label]) =>
            action === 'reject' ? (
              <Button key={action} size="small" variant="outlined" color="error" onClick={() => setRejectOpen(true)}>
                {label}
              </Button>
            ) : (
              <Button
                key={action}
                size="small"
                variant={action === 'cancel' ? 'outlined' : 'contained'}
                onClick={() => transition.mutate({ action })}
                data-testid={`plan-${action}`}
              >
                {label}
              </Button>
            ),
          )}
          <Button size="small" variant="text" component={NextLink} href={`/commercial-planner/cpor-cases/${caseId}`}>
            Settlement workspace
          </Button>
        </Stack>
      </Stack>

      <LifecycleRail
        stages={[...LIFECYCLE_STAGES]}
        labels={STAGE_LABEL}
        current={
          LIFECYCLE_STAGES.includes(data.status as (typeof LIFECYCLE_STAGES)[number])
            ? (data.status as (typeof LIFECYCLE_STAGES)[number])
            : undefined
        }
      />

      <Panel title="Plan parameters" subtitle="Customer, mechanic and window define the case; terms come from the customer’s defaults and can be overridden per line">
        <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(auto-fit, minmax(150px, 1fr))' } }}>
          <TextField size="small" label="Customer" value={data.customer_name ?? ''} disabled />
          <TextField size="small" label="Promotion type" value={data.promotion_type} disabled />
          <TextField size="small" label="Window start" value={data.window_start ?? ''} disabled />
          <TextField size="small" label="Window end" value={data.window_end ?? ''} disabled />
          <TextField
            size="small"
            label="Export template"
            value="Frozen 32-column XLSX"
            disabled
            helperText="Template-driven customer layout is not built"
          />
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          Header fields are editable only in draft or rejected — the same rule as the settlement workspace.
        </Typography>
      </Panel>

      <HeadlineStrip columns={5}>
        <HeadlineFigure
          label="Lines"
          value={lines.length}
          compact
          caption={`${flagCount} flag${flagCount === 1 ? '' : 's'} · none block`}
          severity={flagCount ? 'warn' : 'neutral'}
        />
        <HeadlineFigure label="Estimated units" value={fmtInt(units)} compact caption="Sum of line estimate qty" />
        <HeadlineFigure
          label="Total support"
          value={fmtCompact(support, ccy)}
          compact
          caption={data.ttl_support_usd != null ? `≈ ${fmtCompact(data.ttl_support_usd, 'USD')} USD` : 'Sum of line ttl_support'}
        />
        <HeadlineFigure
          label="Budget after this plan"
          value={budgetPct == null ? '—' : `${budgetPct}%`}
          compact
          severity={overBudget ? 'bad' : budgetPct == null ? 'neutral' : 'good'}
          caption={
            plannedUsd == null
              ? 'No lineup reservation for this case — not estimated'
              : overBudget
                ? 'Over lineup reservation — flagged, not blocked'
                : `${bias?.reservation_source ?? 'lineup-derived'}`
          }
        />
        <HeadlineFigure
          label="On shelf today"
          value="—"
          compact
          caption="Listing activation is not joined onto case lines — open Market & Listings"
        />
      </HeadlineStrip>

      <Panel
        title="Lines"
        subtitle={
          editable
            ? 'Edit SRP, dealer % and units in the grid; dealer price, support and totals recompute on the server. Click a row for the evidence behind it.'
            : 'Read-only at this stage. Click a row for the evidence behind it. Line edits are draft or rejected only.'
        }
        actions={
          <Stack direction="row" spacing={1}>
            <Tooltip title="CIP suggested quantity is not derived — cover and forecast are not joined onto the line" arrow>
              <span>
                <Button size="small" variant="text" disabled data-testid="plan-use-cip-qty">
                  Use CIP quantities
                </Button>
              </span>
            </Tooltip>
            {editable ? (
              <Button size="small" variant="outlined" onClick={() => setAddOpen(true)} data-testid="plan-add-line">
                Add line
              </Button>
            ) : null}
          </Stack>
        }
        flush
      >
        {isMobile ? (
          <Stack spacing={1} sx={{ px: 2, pb: 2 }}>
            {lines.map((l) => (
              <Card key={l.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                <CardActionArea onClick={() => setSelectedLine(l.id)}>
                  <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {l.product_name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {l.product_sku} · SRP {fmtMoney(l.srp, ccy)}
                    </Typography>
                    <Stack direction="row" spacing={2} sx={{ mt: 0.75 }}>
                      <Typography variant="caption">
                        Support/unit <b>{fmtMoney(l.support_unit, ccy)}</b>
                      </Typography>
                      <Typography variant="caption">
                        Units <b>{fmtInt(l.estimate_qty)}</b>
                      </Typography>
                      <Typography variant="caption">
                        Line <b>{fmtCompact(l.ttl_support, ccy)}</b>
                      </Typography>
                    </Stack>
                  </CardContent>
                </CardActionArea>
              </Card>
            ))}
          </Stack>
        ) : (
          <Box sx={{ '& .lab-editable': { bgcolor: theme.palette.mode === 'dark' ? 'rgba(144,202,249,0.08)' : 'rgba(25,118,210,0.05)' } }}>
            <EnterpriseDataGrid<CporCaseLine>
              rowData={lines}
              columnDefs={columnDefs}
              height={280}
              gridOptions={{
                onCellClicked: (e: CellClickedEvent<CporCaseLine>) => e.data && !e.colDef.editable && setSelectedLine(e.data.id),
                onCellValueChanged: onCell,
                getRowId: (p) => String(p.data.id),
                singleClickEdit: true,
                stopEditingWhenCellsLoseFocus: true,
              }}
            />
          </Box>
        )}
      </Panel>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', xl: 'repeat(2, minmax(0, 1fr))' } }}>
        <Panel title="Comparable cases — same customer & family" subtitle="Ranked from stored cases (never a forecast)." flush>
          <Box sx={{ px: 2, pb: 1 }}>
            <CporComparableCasesPanel caseId={caseId} />
          </Box>
        </Panel>
        <Panel title="Where this plan draws from" subtitle="Cross-domain evidence, each a link to its owning workflow" flush>
          <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
            <PanelRow
              severity="neutral"
              primary="Stock cover per line"
              secondary="Cover is derived SOH — not stored on the case line"
              figure="Stock & Sell-through"
              onClick={() => router.push('/stock?lens=cover')}
            />
            <PanelRow
              severity="neutral"
              primary="Lineup forecast & budget reservation"
              secondary={plannedUsd == null ? 'No reservation in scope for this case' : `${bias?.reservation_source ?? 'derived_from_profit'}`}
              figure="Planning"
              onClick={() => router.push('/commercial-planner')}
            />
            <PanelRow
              severity="neutral"
              primary="Listings for these SKUs"
              secondary="Activation vs covering line SRP lives in Market & Listings, not on this grid"
              figure="Market & Listings"
              onClick={() => router.push('/listing-capture?tab=registry')}
            />
            <PanelRow
              severity="neutral"
              primary="Competitor products"
              secondary="Product-vs-product mappings — nothing inferred about customers"
              figure="Market › Competition"
              onClick={() => router.push('/competition?tab=mappings')}
            />
            <PanelRow
              severity="neutral"
              primary="Customer terms"
              secondary="Dealer margin and rebate defaults feeding the waterfall"
              figure="Terms & assumptions"
              onClick={() => router.push('/admin/customer-commercial-terms')}
            />
          </Stack>
        </Panel>
      </Box>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
        <Panel title="Validation" subtitle="Flags explain; they never block a save." flush>
          <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
            {lines.flatMap((l) => (l.flags ?? []).map((f) => ({ l, f }))).map(({ l, f }) => (
              <PanelRow
                key={`${l.id}-${f}`}
                severity={f.startsWith('no_cost') ? 'danger' : 'warning'}
                primary={l.product_sku ?? String(l.id)}
                secondary={f}
                onClick={() => setSelectedLine(l.id)}
              />
            ))}
            {overBudget ? (
              <PanelRow severity="warning" primary="Budget" secondary={`Plan takes reservation to ${budgetPct}% — soft check`} />
            ) : null}
            {!flagCount && !overBudget ? (
              <Stack direction="row" spacing={1} alignItems="center" sx={{ px: 1.5, py: 1 }}>
                <CheckCircleOutlineIcon fontSize="small" color="success" />
                <Typography variant="body2">No flags on this plan.</Typography>
              </Stack>
            ) : null}
          </Stack>
        </Panel>
        <Panel title="Export target" subtitle="The plan leaves CIP as a versioned workbook recorded on the case">
          <Stack spacing={1} sx={{ px: 1.5, pb: 1.5 }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Frozen 32-column XLSX
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Template-driven export is not built. Export downloads the one layout compiled in code —
              not the customer&apos;s promotion-plan format, even when an import profile exists.
            </Typography>
          </Stack>
        </Panel>
      </Box>
      <CapabilityLedger items={PLANNER_CAPABILITIES.slice(0, 5)} title="What works on this screen" />

      <LineEvidencePanel line={line} caseCode={data.case_code} currency={ccy} caseId={caseId} onClose={() => setSelectedLine(null)} />

      <Dialog open={rejectOpen} onClose={() => setRejectOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Reject {data.case_code}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Proposed cannot return to draft. Reject records a reason; the author can resend.
          </Typography>
          <TextField
            label="Comment"
            value={rejectComment}
            onChange={(e) => setRejectComment(e.target.value)}
            fullWidth
            multiline
            minRows={2}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejectOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="error"
            disabled={!rejectComment.trim()}
            onClick={() => transition.mutate({ action: 'reject', comment: rejectComment.trim() })}
          >
            Reject
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={exportOpen} onClose={() => setExportOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Export {data.case_code}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <Typography variant="body2" color="text.secondary">
              This records a versioned XLSX on the case so later approvals refer to an exact file.
              The layout is one frozen 32-column tuple in code.
            </Typography>
            <Alert severity="warning" variant="outlined">
              Template-driven export is not built. This is not the customer&apos;s promotion-plan
              workbook layout. The import side of a mapping profile already exists; export does not
              consume it.
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExportOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={exportCase.isPending}
            onClick={() => {
              setExportOpen(false);
              exportCase.mutate();
            }}
            data-testid="plan-export-confirm"
          >
            Export XLSX
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={addOpen} onClose={() => !addLine.isPending && setAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add line</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <EntitySearchAutocomplete<ProductPick>
              label="Product"
              value={product}
              onChange={setProduct}
              getOptionLabel={(o) => `${o.sku} — ${o.name}`}
              fetchOptions={async (query, signal) => {
                const q = query.trim();
                const res = await apiGet<{ items: ProductPick[] }>(
                  `/api/v1/products?page=1&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ''}`,
                  { signal },
                );
                return res.items ?? [];
              }}
            />
            <TextField size="small" label="Promo SRP" value={srp} onChange={(e) => setSrp(e.target.value)} />
            <TextField size="small" label="Estimate qty" value={estimate} onChange={(e) => setEstimate(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!product || addLine.isPending} onClick={() => addLine.mutate()}>
            Add
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={!!toast} autoHideDuration={4500} onClose={() => setToast(null)} message={toast} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Stack>
  );
}

function LineEvidencePanel({
  line,
  caseCode,
  currency,
  caseId,
  onClose,
}: {
  line: CporCaseLine | null;
  caseCode: string;
  currency: string;
  caseId: number;
  onClose: () => void;
}) {
  const { data: suggest } = useQuery({
    queryKey: ['cpor', 'cost-suggest', caseId, line?.id],
    queryFn: ({ signal }) =>
      apiGet<{
        cost_basis: number | null;
        cost_source: string | null;
        stored_cost_basis: number | null;
        flags: string[];
      }>(`/api/v1/cpor/cases/${caseId}/lines/${line!.id}/cost-suggest`, { signal }),
    enabled: !!line,
  });

  return (
    <EntityContextPanel
      open={!!line}
      onClose={onClose}
      kicker={line ? `${caseCode} · line ${line.id}` : undefined}
      title={line ? (line.product_name ?? line.product_sku ?? '') : ''}
      subtitle={line ? `${line.product_sku} · layer ${line.pod_quarter ?? '—'}` : undefined}
      width={500}
      figures={
        line ? (
          <HeadlineStrip columns={3}>
            <HeadlineFigure label="Support / unit" value={fmtMoney(line.support_unit, currency)} dense />
            <HeadlineFigure label="Dealer price" value={fmtMoney(line.dealer_price, currency)} dense />
            <HeadlineFigure
              label="Line support"
              value={fmtCompact(line.ttl_support, currency)}
              dense
              caption={`${fmtInt(line.estimate_qty)} units`}
            />
          </HeadlineStrip>
        ) : null
      }
      related={
        line
          ? [
              { label: 'Stock cover & sell-through', href: '/stock?lens=cover', hint: 'Stock & Sell-through' },
              { label: 'Monitored listings for this SKU', href: '/listing-capture?tab=registry', hint: 'Market & Listings' },
              {
                label: 'Competitor mappings',
                href: '/competition?tab=mappings',
                hint: 'Market › Competition · product vs product',
              },
              { label: 'Product master', href: '/admin/products', hint: 'Data & Stewardship' },
            ]
          : []
      }
      footer={line ? <Button variant="outlined" size="small" onClick={onClose}>Close</Button> : null}
    >
      {line ? (
        <Stack spacing={2.5}>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Waterfall
            </Typography>
            <KeyValueList
              items={[
                { k: 'Promo SRP', v: fmtMoney(line.srp, currency) },
                { k: 'Dealer %', v: fmtPct(line.dealer_margin_pct) },
                { k: 'Dealer price', v: fmtMoney(line.dealer_price, currency) },
                { k: 'Cost basis', v: `${fmtMoney(line.cost_basis, currency)} · ${line.cost_source ?? '—'}` },
                { k: 'Support / unit', v: <b>{fmtMoney(line.support_unit, currency)}</b> },
              ]}
            />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Cost suggestion
            </Typography>
            <KeyValueList
              items={[
                { k: 'Stored', v: fmtMoney(suggest?.stored_cost_basis ?? line.cost_basis, currency) },
                { k: 'Suggested', v: fmtMoney(suggest?.cost_basis ?? null, currency) },
                { k: 'Source', v: suggest?.cost_source ?? '—' },
              ]}
            />
          </Box>
          {(line.flags ?? []).length ? (
            <Alert severity="warning" variant="outlined">
              {line.flags.map((f) => (
                <Typography key={f} variant="body2">
                  {f}
                </Typography>
              ))}
            </Alert>
          ) : null}
        </Stack>
      ) : null}
    </EntityContextPanel>
  );
}
