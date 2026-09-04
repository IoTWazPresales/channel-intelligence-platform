'use client';

import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import type { ColDef, RowClickedEvent } from 'ag-grid-community';
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
  MenuItem,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { PromoPlanBuilderPanel } from '@/app/(app)/promotions/PromoPlanBuilderPanel';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { PLANNER_CAPABILITIES } from '@/features/promotions-funding/capabilities';
import { fmtCompact, fmtInt } from '@/features/promotions-funding/format';
import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import {
  countPlanning,
  LIFECYCLE_STAGES,
  ORIGIN_LABEL,
  STAGE_LABEL,
  stageTone,
  type PlanStage,
} from '@/features/promotions-funding/lifecycle';
import { PlanWorkspace } from '@/features/promotions-funding/PlanWorkspace';
import type { CporCaseListRow, CporCasesPage, SupportBiasRead } from '@/features/promotions-funding/types';
import { apiGet, apiPost } from '@/lib/api';
import { CapabilityLedger } from '@/features/workbench-ui/CapabilityLedger';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { LifecycleRail } from '@/features/workbench-ui/LifecycleRail';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { ScopeBar, StatusChip } from '@/features/workbench-ui/controls';

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type PromoTypes = { promotion_types: string[] };

export function PromotionPlannerSurface() {
  const router = useRouter();
  const search = useSearchParams();
  const planId = Number(search.get('plan') || '');
  const stageFilter = (search.get('stage') as PlanStage | null) || null;
  const setParam = useCallback(
    (k: string, v: string | null) => {
      const next = new URLSearchParams(search.toString());
      if (v === null || v === '') next.delete(k);
      else next.set(k, v);
      const qs = next.toString();
      router.replace(qs ? `/promotions?${qs}` : '/promotions', { scroll: false });
    },
    [router, search],
  );

  if (Number.isFinite(planId) && planId > 0) {
    return (
      <Box data-testid="promotion-planner">
        <FundingChrome />
        <PlanWorkspace caseId={planId} onBack={() => setParam('plan', null)} />
      </Box>
    );
  }

  return (
    <PlannerList
      stageFilter={stageFilter}
      newRequested={search.get('new') === '1'}
      setParam={setParam}
      onOpen={(id) => setParam('plan', String(id))}
    />
  );
}

function PlannerList({
  stageFilter,
  newRequested,
  setParam,
  onOpen,
}: {
  stageFilter: PlanStage | null;
  newRequested: boolean;
  setParam: (k: string, v: string | null) => void;
  onOpen: (id: number) => void;
}) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'), { noSsr: true });
  const router = useRouter();
  const qc = useQueryClient();
  const [proposeOpen, setProposeOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (newRequested) setCreateOpen(true);
  }, [newRequested]);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['cpor', 'cases', 'planner', stageFilter],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams({ page: '1', page_size: '200' });
      if (stageFilter) sp.set('status', stageFilter);
      return apiGet<CporCasesPage>(`/api/v1/cpor/cases?${sp.toString()}`, { signal });
    },
  });

  const { data: proposedPage } = useQuery({
    queryKey: ['cpor', 'cases', 'planner', 'proposed'],
    queryFn: ({ signal }) =>
      apiGet<CporCasesPage>('/api/v1/cpor/cases?page=1&page_size=20&status=proposed', { signal }),
  });

  const { data: endedPage } = useQuery({
    queryKey: ['cpor', 'cases', 'planner', 'ended'],
    queryFn: ({ signal }) =>
      apiGet<CporCasesPage>('/api/v1/cpor/cases?page=1&page_size=200&status=ended', { signal }),
  });

  const { data: bias } = useQuery({
    queryKey: ['cpor', 'support-bias', 'planner'],
    queryFn: ({ signal }) => apiGet<SupportBiasRead>('/api/v1/cpor/intelligence/support-bias', { signal }),
  });

  const counts = data?.status_counts ?? {};
  const rows = data?.items ?? [];
  const planningN = countPlanning(counts);
  const liveN = counts.active ?? 0;
  const proposedN = counts.proposed ?? 0;
  const reviewN = data?.review_queue_count ?? proposedN;
  const plannedUsd = bias?.totals?.planned_usd ?? null;
  const drawnUsd = bias?.totals?.actual_usd ?? null;
  const budgetPct =
    plannedUsd && plannedUsd > 0 && drawnUsd != null ? Math.round((drawnUsd / plannedUsd) * 100) : null;

  const inPlanningSupport = rows
    .filter((r) => ['draft', 'proposed', 'approved', 'rejected'].includes(r.status))
    .reduce((n, r) => n + (Number(r.ttl_support_zar) || 0), 0);

  return (
    <Box data-testid="promotion-planner">
      <FundingChrome />
      <Stack spacing={2} sx={{ mt: 2 }}>
        <Alert severity="info" variant="outlined" icon={false} sx={{ '& .MuiAlert-message': { width: '100%' } }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }} justifyContent="space-between">
            <Typography variant="body2">
              <b>One case, one lifecycle.</b> A promotion plan you author here is the same case the Case book
              approves, watches live, claims and settles. Nothing is copied between “plan” and “funding”.
            </Typography>
            <Box sx={{ minWidth: { md: 520 } }}>
              <LifecycleRail
                stages={[...LIFECYCLE_STAGES]}
                labels={STAGE_LABEL}
                counts={counts}
                dense
                onSelect={(s) => setParam('stage', stageFilter === s ? null : s)}
              />
            </Box>
          </Stack>
        </Alert>

        <HeadlineStrip columns={5}>
          <HeadlineFigure
            label="In planning"
            value={planningN}
            unit="plans"
            compact
            caption={`${fmtCompact(inPlanningSupport)} support on this page`}
            onClick={() => setParam('stage', 'proposed')}
          />
          <HeadlineFigure
            label="Live now"
            value={liveN}
            unit="plans"
            compact
            onClick={() => setParam('stage', 'active')}
          />
          <HeadlineFigure
            label="Awaiting your review"
            value={reviewN}
            unit="cases"
            compact
            severity={reviewN ? 'warn' : 'neutral'}
            caption="Proposed, or flagged for reapproval — not ended cases waiting on claims"
            onClick={() => setParam('stage', 'proposed')}
          />
          <HeadlineFigure
            label="Budget reservation used"
            value={budgetPct == null ? '—' : `${budgetPct}%`}
            compact
            caption={
              plannedUsd == null
                ? 'No lineup-derived reservation in scope'
                : `${fmtCompact(drawnUsd, 'USD')} of ${fmtCompact(plannedUsd, 'USD')} · lineup-derived on SKU-economics lines`
            }
            severity={budgetPct != null && budgetPct > 85 ? 'warn' : 'neutral'}
          />
          <HeadlineFigure
            label="Uplift / effectiveness"
            value="—"
            compact
            caption="Not derived until ≥5 settled cases with claim evidence — never estimated"
          />
        </HeadlineStrip>

        <Box
          sx={{
            display: 'grid',
            gap: 2,
            gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 3fr) minmax(300px, 2fr)' },
            alignItems: 'start',
          }}
        >
          <Stack spacing={2} sx={{ minWidth: 0 }}>
            <ScopeBar
              chips={LIFECYCLE_STAGES.map((s) => ({
                key: s,
                label: `${STAGE_LABEL[s]} · ${counts[s] ?? 0}`,
                active: stageFilter === s,
                onToggle: () => setParam('stage', stageFilter === s ? null : s),
                tone: s === 'active' ? 'success' : s === 'proposed' ? 'warning' : 'default',
              }))}
              summary={`${rows.length} of ${data?.total ?? rows.length} plans`}
              onClear={() => setParam('stage', null)}
              trailing={
                <Stack direction="row" spacing={1}>
                  <Tooltip title="Partly built: the proposal still needs a seed case id. Attention will surface this gap; it is not a separate work container." arrow>
                    <span>
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<AutoAwesomeOutlinedIcon />}
                        onClick={() => setProposeOpen(true)}
                        data-testid="planner-propose"
                      >
                        Propose a plan
                      </Button>
                    </span>
                  </Tooltip>
                  <Button size="small" variant="contained" onClick={() => setCreateOpen(true)} data-testid="planner-new">
                    New plan
                  </Button>
                </Stack>
              }
            />
            <ModuleDataSection
              isLoading={isLoading}
              isError={isError}
              error={error as Error | null}
              onRetry={() => void refetch()}
              isEmpty={rows.length === 0}
              empty={{
                title: 'No plans in this stage',
                description: 'Clear the stage filter, propose a plan from evidence, or start one manually.',
                primary: { label: 'Clear', onClick: () => setParam('stage', null) },
              }}
            >
              {isMobile ? (
                <Stack spacing={1} data-testid="planner-record-cards">
                  {rows.map((p) => (
                    <Card key={p.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                      <CardActionArea onClick={() => onOpen(p.id)}>
                        <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                            <Box sx={{ minWidth: 0 }}>
                              <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                                {p.case_name || p.case_code}
                              </Typography>
                              <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                                {p.case_code} · {p.customer_name} · {p.window_start} → {p.window_end}
                              </Typography>
                            </Box>
                            <StatusChip label={STAGE_LABEL[p.status as PlanStage] ?? p.status} tone={stageTone(p.status)} />
                          </Stack>
                          <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
                            <Typography variant="caption">
                              Lines <b>{p.line_count ?? 0}</b>
                            </Typography>
                            <Typography variant="caption">
                              Units <b>{fmtInt(p.estimate_qty_sum)}</b>
                            </Typography>
                            <Typography variant="caption">
                              Support <b>{fmtCompact(p.ttl_support_zar, p.currency_code)}</b>
                            </Typography>
                          </Stack>
                        </CardContent>
                      </CardActionArea>
                    </Card>
                  ))}
                </Stack>
              ) : (
                <PlanGrid rows={rows} onOpen={onOpen} />
              )}
            </ModuleDataSection>
          </Stack>

          <Stack spacing={2}>
            <Panel title="Needs a decision" subtitle="Grouped by condition, then ranked" flush>
              <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                {(() => {
                  const seen = new Set<number>();
                  const reapproval = [...(data?.items ?? []), ...(endedPage?.items ?? []), ...(proposedPage?.items ?? [])].filter(
                    (p) => {
                      if (!p.needs_reapproval || seen.has(p.id)) return false;
                      seen.add(p.id);
                      return true;
                    },
                  );
                  const n = reapproval.length;
                  if (!n) return null;
                  const one = n === 1 ? reapproval[0] : null;
                  return (
                    <PanelRow
                      severity="warning"
                      primary={
                        one
                          ? `${one.case_code} · reapproval required`
                          : `${n} cases flagged for reapproval`
                      }
                      secondary="Money-ceiling reapproval — not the same as Proposed, and not claim evidence."
                      figure="Case book"
                      onClick={() => {
                        if (one) onOpen(one.id);
                        else router.push('/commercial-planner/cpor-cases');
                      }}
                    />
                  );
                })()}
                {proposedN > 0 ? (
                  <PanelRow
                    severity="warning"
                    primary={
                      proposedN === 1
                        ? `${proposedPage?.items?.[0]?.case_code ?? 'Proposal'} · review proposal`
                        : `${proposedN} proposals need a review`
                    }
                    secondary={
                      proposedN === 1
                        ? `${proposedPage?.items?.[0]?.customer_name ?? ''} · ${proposedPage?.items?.[0]?.line_count ?? 0} lines · ${fmtCompact(proposedPage?.items?.[0]?.ttl_support_zar, proposedPage?.items?.[0]?.currency_code)}`
                        : 'CIP and planner proposals in Proposed — open the planner filter'
                    }
                    onClick={() => {
                      if (proposedN === 1 && proposedPage?.items?.[0]) onOpen(proposedPage.items[0].id);
                      else setParam('stage', 'proposed');
                    }}
                  />
                ) : null}
                {(() => {
                  const pending = (endedPage?.items ?? []).filter(
                    (p) => (p.settle_readiness?.claim_evidence_count ?? 0) === 0,
                  );
                  const n = pending.length;
                  if (!n) return null;
                  return (
                    <PanelRow
                      severity="info"
                      primary={`${n} ended cases · claim evidence pending`}
                      secondary="One condition: the window ended and no claim file is applied. Open the case book on Ended."
                      figure="Case book"
                      onClick={() => router.push('/commercial-planner/cpor-cases?status=ended')}
                    />
                  );
                })()}
                {!proposedN &&
                !(endedPage?.items ?? []).some((p) => p.needs_reapproval) &&
                !(endedPage?.items ?? []).some((p) => (p.settle_readiness?.claim_evidence_count ?? 0) === 0) ? (
                  <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
                    Nothing waiting on you.
                  </Typography>
                ) : null}
              </Stack>
            </Panel>
            <CapabilityLedger items={PLANNER_CAPABILITIES} />
          </Stack>
        </Box>
      </Stack>

      <Dialog open={proposeOpen} onClose={() => setProposeOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>Propose a plan</DialogTitle>
        <DialogContent>
          <PromoPlanBuilderPanel />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setProposeOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      <CreateCaseDialog
        open={createOpen}
        onClose={() => {
          setCreateOpen(false);
          if (newRequested) setParam('new', null);
        }}
        onCreated={(id) => {
          setCreateOpen(false);
          void qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
          onOpen(id);
        }}
        onError={(m) => setToast(m)}
      />
      <Snackbar open={!!toast} autoHideDuration={4000} onClose={() => setToast(null)} message={toast} />
    </Box>
  );
}

function PlanGrid({ rows, onOpen }: { rows: CporCaseListRow[]; onOpen: (id: number) => void }) {
  const columnDefs = useMemo<ColDef<CporCaseListRow>[]>(
    () => [
      { field: 'case_code', headerName: 'Case', width: 130, pinned: 'left' },
      {
        field: 'case_name',
        headerName: 'Plan',
        minWidth: 220,
        flex: 1.6,
        cellRenderer: (p: { data?: CporCaseListRow }) =>
          p.data ? (
            <Box sx={{ lineHeight: 1.2 }}>
              <Typography variant="body2" noWrap>
                {p.data.case_name || p.data.case_code}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {p.data.customer_name} · {p.data.promotion_type}
              </Typography>
            </Box>
          ) : null,
      },
      {
        colId: 'window',
        headerName: 'Window',
        minWidth: 180,
        flex: 1,
        valueGetter: (p) => (p.data ? `${p.data.window_start ?? ''} → ${p.data.window_end ?? ''}` : ''),
      },
      {
        field: 'status',
        headerName: 'Stage',
        width: 120,
        cellRenderer: (p: { data?: CporCaseListRow }) =>
          p.data ? (
            <StatusChip label={STAGE_LABEL[p.data.status as PlanStage] ?? p.data.status} tone={stageTone(p.data.status)} />
          ) : null,
      },
      {
        field: 'origin',
        headerName: 'Origin',
        width: 150,
        valueFormatter: (p) => ORIGIN_LABEL[String(p.value ?? 'native')] ?? String(p.value ?? ''),
      },
      { field: 'line_count', headerName: 'Lines', type: 'rightAligned', width: 80 },
      {
        field: 'estimate_qty_sum',
        headerName: 'Est. units',
        type: 'rightAligned',
        width: 110,
        valueFormatter: (p) => fmtInt(p.value as number | null),
      },
      {
        field: 'ttl_support_zar',
        headerName: 'Support',
        type: 'rightAligned',
        width: 120,
        valueFormatter: (p) => fmtCompact(p.value as number | null, p.data?.currency_code),
      },
    ],
    [],
  );
  return (
    <EnterpriseDataGrid<CporCaseListRow>
      rowData={rows}
      columnDefs={columnDefs}
      height={400}
      gridOptions={{
        onRowClicked: (e: RowClickedEvent<CporCaseListRow>) => e.data && onOpen(e.data.id),
        getRowId: (p) => String(p.data.id),
      }}
    />
  );
}

function CreateCaseDialog({
  open,
  onClose,
  onCreated,
  onError,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: number) => void;
  onError: (m: string) => void;
}) {
  const [cust, setCust] = useState<CustomerPick | null>(null);
  const [promoType, setPromoType] = useState('Sell out PP');
  const [windowStart, setWindowStart] = useState('');
  const [windowEnd, setWindowEnd] = useState('');
  const { data: types } = useQuery({
    queryKey: ['cpor', 'promotion-types'],
    queryFn: ({ signal }) => apiGet<PromoTypes>('/api/v1/cpor/meta/promotion-types', { signal }),
    enabled: open,
  });
  const create = useMutation({
    mutationFn: () =>
      apiPost<{ id: number }>('/api/v1/cpor/cases', {
        customer_id: cust!.id,
        promotion_type: promoType,
        window_start: windowStart,
        window_end: windowEnd,
      }),
    onSuccess: (row) => onCreated(row.id),
    onError: (e) => onError(e instanceof Error ? e.message : String(e)),
  });
  return (
    <Dialog open={open} onClose={() => !create.isPending && onClose()} fullWidth maxWidth="sm">
      <DialogTitle>New promotion plan</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ pt: 1 }}>
          <EntitySearchAutocomplete<CustomerPick>
            label="Customer"
            value={cust}
            onChange={setCust}
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
          <TextField select size="small" label="Promotion type" value={promoType} onChange={(e) => setPromoType(e.target.value)} fullWidth>
            {(types?.promotion_types ?? ['Sell out PP']).map((t) => (
              <MenuItem key={t} value={t}>
                {t}
              </MenuItem>
            ))}
          </TextField>
          <TextField size="small" type="date" label="Window start" InputLabelProps={{ shrink: true }} value={windowStart} onChange={(e) => setWindowStart(e.target.value)} fullWidth />
          <TextField size="small" type="date" label="Window end" InputLabelProps={{ shrink: true }} value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} fullWidth />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={create.isPending}>
          Cancel
        </Button>
        <Button
          variant="contained"
          disabled={!cust || !windowStart || !windowEnd || create.isPending}
          onClick={() => create.mutate()}
        >
          Create
        </Button>
      </DialogActions>
    </Dialog>
  );
}
