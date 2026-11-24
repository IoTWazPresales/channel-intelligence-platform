'use client';

import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import CloseIcon from '@mui/icons-material/Close';
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
  Drawer,
  IconButton,
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
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { PromoPlanBuilderPanel } from '@/app/(app)/promotions/PromoPlanBuilderPanel';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { AgedStockPanel } from '@/features/promotions-funding/AgedStockPanel';
import { CaseScopeFilters } from '@/features/promotions-funding/CaseScopeFilters';
import {
  caseScopeClearPatch,
  caseScopeFromSearch,
  caseScopeIsActive,
  caseScopeToQuery,
} from '@/features/promotions-funding/caseScope';
import { PLANNER_CAPABILITIES } from '@/features/promotions-funding/capabilities';
import { formatDualMoneyLine } from '@/features/cpor/fxDisplay';
import { fmtCompact, fmtInt } from '@/features/promotions-funding/format';
import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import {
  countPlanning,
  LIFECYCLE_STAGES,
  ORIGIN_LABEL,
  PLANNING_STAGES,
  STAGE_LABEL,
  stageTone,
  type PlanStage,
} from '@/features/promotions-funding/lifecycle';
import { PlanWorkspace } from '@/features/promotions-funding/PlanWorkspace';
import {
  awaitingCountUrl,
  BASE_COUNTS_URL,
  calendarClashUrl,
  clashCardFigure,
  pageIsComplete,
  startingCountUrl,
  statusCount,
  todayIso,
  unplannedAgedStock,
  type AgedStockResponseLike,
  type CalendarClashSummary,
  type CaseCounts,
} from '@/features/promotions-funding/plannerCards';
import { buildActionQueue, queueSummary } from '@/features/promotions-funding/plannerLayout/actionQueue';
import { CustomerRowsTimeline } from '@/features/promotions-funding/planner/CustomerRowsTimeline';
import { withPlannerCalendarScope } from '@/features/promotions-funding/planner/plannerCalendarScope';
import { PlannerDetailPanel } from '@/features/promotions-funding/planner/PlannerDetailPanel';
import { PlannerKpiCard } from '@/features/promotions-funding/planner/PlannerKpiCard';
import { PlannerQueueSection, type PlannerQueueCard } from '@/features/promotions-funding/planner/PlannerQueueSection';
import type { CporCaseListRow, CporCasesPage } from '@/features/promotions-funding/types';
import { clashSummaryKey, invalidateClashSummary } from '@/features/promotions-funding/calendarClashKeys';
import { apiGet, apiPost } from '@/lib/api';
import { CapabilityLedger } from '@/features/workbench-ui/CapabilityLedger';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { LifecycleRail } from '@/features/workbench-ui/LifecycleRail';
import { Panel } from '@/features/workbench-ui/Panel';
import { ScopeBar, StatusChip } from '@/features/workbench-ui/controls';

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type PromoTypes = { promotion_types: string[] };

export function PromotionPlannerSurface() {
  const router = useRouter();
  const search = useSearchParams();
  const planId = Number(search.get('plan') || '');
  const stageFilter = (search.get('stage') as PlanStage | null) || null;
  const testDataOnly = search.get('test_data') === 'only';
  const scope = caseScopeFromSearch(search);
  const setParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(search.toString());
      Object.entries(patch).forEach(([k, v]) => (v == null || v === '' ? next.delete(k) : next.set(k, v)));
      const qs = next.toString();
      router.replace(qs ? `/promotions?${qs}` : '/promotions', { scroll: false });
    },
    [router, search],
  );
  const setParam = useCallback(
    (k: string, v: string | null) => setParams({ [k]: v }),
    [setParams],
  );

  if (Number.isFinite(planId) && planId > 0) {
    return (
      <Box data-testid="promotion-planner">
        <FundingChrome>
          <PlanWorkspace caseId={planId} onBack={() => setParam('plan', null)} />
        </FundingChrome>
      </Box>
    );
  }

  return (
    <PlannerList
      stageFilter={stageFilter}
      scope={scope}
      testDataOnly={testDataOnly}
      newRequested={search.get('new') === '1'}
      proposeRequested={search.get('propose') === '1'}
      setParam={setParam}
      setParams={setParams}
      onOpen={(id) => setParam('plan', String(id))}
    />
  );
}

function PlannerList({
  stageFilter,
  scope,
  testDataOnly,
  newRequested,
  proposeRequested,
  setParam,
  setParams,
  onOpen,
}: {
  stageFilter: PlanStage | null;
  scope: ReturnType<typeof caseScopeFromSearch>;
  testDataOnly: boolean;
  newRequested: boolean;
  proposeRequested: boolean;
  setParam: (k: string, v: string | null) => void;
  setParams: (patch: Record<string, string | null>) => void;
  onOpen: (id: number) => void;
}) {
  const theme = useTheme();
  const router = useRouter();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'), { noSsr: true });
  const qc = useQueryClient();
  const [proposeOpen, setProposeOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (newRequested) setCreateOpen(true);
  }, [newRequested]);
  useEffect(() => {
    if (proposeRequested) setProposeOpen(true);
  }, [proposeRequested]);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['cpor', 'cases', 'planner', 'reporting-calendar', stageFilter, scope, testDataOnly],
    queryFn: ({ signal }) => {
      const sp = withPlannerCalendarScope(new URLSearchParams({ page: '1', page_size: '500' }));
      if (stageFilter) sp.set('status', stageFilter);
      if (testDataOnly) sp.set('test_data', 'only');
      caseScopeToQuery(scope).forEach((v, k) => sp.set(k, v));
      return apiGet<CporCasesPage>(`/api/v1/cpor/cases?${sp.toString()}`, { signal });
    },
  });

  const {
    data: proposedPage,
    isLoading: proposedLoading,
    isError: proposedError,
    refetch: refetchProposed,
  } = useQuery({
    queryKey: ['cpor', 'cases', 'planner', 'proposed'],
    queryFn: ({ signal }) =>
      apiGet<CporCasesPage>('/api/v1/cpor/cases?page=1&page_size=500&status=proposed', { signal }),
  });

  const {
    data: endedPage,
    isLoading: endedLoading,
    isError: endedError,
    refetch: refetchEnded,
  } = useQuery({
    queryKey: ['cpor', 'cases', 'planner', 'ended'],
    queryFn: ({ signal }) =>
      apiGet<CporCasesPage>('/api/v1/cpor/cases?page=1&page_size=500&status=ended', { signal }),
  });

  // The local calendar day, re-read every minute so the rolling window and today marker follow midnight.
  const [today, setToday] = useState(() => todayIso());
  useEffect(() => {
    const timer = setInterval(() => {
      const now = todayIso();
      setToday((prev) => (prev === now ? prev : now));
    }, 60_000);
    return () => clearInterval(timer);
  }, []);

  // Exact counts (Warren 2026-11-19): `GET /cpor/cases/counts` counts current cases only (replaced cases left out)
  // and is not capped by a page size. The cards are independent of the stage chips, so they do not move with them.
  const startingReq = startingCountUrl(today);
  const {
    data: baseCounts,
    isLoading: baseCountsLoading,
    isError: baseCountsError,
    refetch: refetchBaseCounts,
  } = useQuery({
    queryKey: ['cpor', 'cases', 'counts', 'base'],
    queryFn: ({ signal }) => apiGet<CaseCounts>(BASE_COUNTS_URL, { signal }),
  });
  const {
    data: awaitingCounts,
    isLoading: awaitingLoading,
    isError: awaitingError,
    refetch: refetchAwaiting,
  } = useQuery({
    queryKey: ['cpor', 'cases', 'counts', 'proposed'],
    queryFn: ({ signal }) => apiGet<CaseCounts>(awaitingCountUrl(), { signal }),
  });
  const {
    data: startingCounts,
    isLoading: startingLoading,
    isError: startingError,
    refetch: refetchStarting,
  } = useQuery({
    queryKey: ['cpor', 'cases', 'counts', 'starting', today],
    queryFn: ({ signal }) => apiGet<CaseCounts>(startingReq.url, { signal }),
  });
  // Our open promotions that clash with a customer's calendar events (tenant-wide, exact).
  const {
    data: clashData,
    isLoading: clashLoading,
    isError: clashError,
    refetch: refetchClash,
  } = useQuery({
    queryKey: [...clashSummaryKey(today)],
    queryFn: ({ signal }) => apiGet<CalendarClashSummary>(calendarClashUrl(today), { signal }),
  });

  // Same query key and URL as AgedStockPanel, so the card and the panel share one request.
  const aged = useQuery({
    queryKey: ['cpor', 'aged-stock'],
    queryFn: ({ signal }) =>
      apiGet<AgedStockResponseLike>('/api/v1/cpor/intelligence/promo-plan-draft/aged-stock', { signal }),
  });

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const detailOpen = selectedId != null;
  const closeDetail = useCallback(() => setSelectedId(null), []);

  const counts = data?.status_counts ?? {};
  const rowsAll = data?.items ?? [];
  const rows = rowsAll;
  // The stage chips and the lifecycle rail above keep the list's `status_counts` (the whole book, replaced cases
  // included); the headline cards read the exact current-case counts.
  const draftsN = statusCount(baseCounts, 'draft');
  const endedN = statusCount(baseCounts, 'ended');
  const planningN = countPlanning(counts);
  const bookN = Object.values(counts).reduce((n, v) => n + (Number(v) || 0), 0);

  const awaitingN = awaitingCounts?.total_current ?? null;
  const startingN = startingCounts?.total_current ?? null;
  // A figure is only a figure once its request succeeded: loading and failed requests never read as zero.
  const figureState = (loading: boolean, failed: boolean): 'loading' | 'empty' | 'ready' =>
    loading ? 'loading' : failed ? 'empty' : 'ready';
  const awaitingState = figureState(awaitingLoading, awaitingError);
  const startingState = figureState(startingLoading, startingError);
  const countsState = figureState(baseCountsLoading, baseCountsError);
  const clashState = figureState(clashLoading, clashError);
  const clash = clashData ? clashCardFigure(clashData) : null;
  const queueUnavailable = [
    ...(isError ? ['Case list'] : []),
    ...(proposedError ? ['Awaiting approval'] : []),
    ...(endedError ? ['Ended cases'] : []),
  ];
  // Each queue source fetches the first 500 rows; if any source has more, an empty queue is not confirmed.
  const queueIncomplete =
    (data != null && !pageIsComplete(data)) ||
    (proposedPage != null && !pageIsComplete(proposedPage)) ||
    (endedPage != null && !pageIsComplete(endedPage));
  const retryQueue = () => {
    if (isError) void refetch();
    if (proposedError) void refetchProposed();
    if (endedError) void refetchEnded();
  };
  const agedUnplanned = unplannedAgedStock(aged.data);
  const queue = useMemo(
    () =>
      buildActionQueue({
        cases: data?.items ?? [],
        proposed: proposedPage?.items ?? [],
        ended: endedPage?.items ?? [],
        today,
      }),
    [data?.items, proposedPage?.items, endedPage?.items, today],
  );
  const queueTotals = queueSummary(queue);
  const queueLoading = isLoading || proposedLoading || endedLoading;
  // A queue figure is only a figure when every source loaded; a partial queue says so in the caption.
  const queueFigureState: 'loading' | 'empty' | 'ready' = queueLoading
    ? 'loading'
    : queueUnavailable.length > 0
      ? 'empty'
      : 'ready';
  const queueCaptionNote = queueIncomplete ? ' (first 500 cases of each list)' : '';
  // In planning / Live promotions read the exact current-case counts, like the cards beside them.
  const planningCount =
    baseCounts == null
      ? null
      : PLANNING_STAGES.reduce((n, st) => n + (statusCount(baseCounts, st) ?? 0), 0);
  const liveCount = statusCount(baseCounts, 'active');
  const queueCards: PlannerQueueCard[] = [
    {
      key: 'overdue',
      label: 'Overdue approvals',
      value: queueFigureState === 'ready' ? queueTotals.overdueApprovals : null,
      state: queueFigureState,
      tone: 'warning',
      caption:
        queueFigureState === 'empty'
          ? 'Could not be loaded. Click to retry.'
          : `Awaiting approval with the window already started${queueCaptionNote}`,
      onClick: queueFigureState === 'empty' ? retryQueue : () => setParam('stage', 'proposed'),
    },
    {
      key: 'low-stock',
      label: 'Low stock risk',
      value: null,
      state: 'unavailable',
      caption:
        'Sell-through stock cover is used when proposing lines, but no per-promotion low-stock figure is read here yet.',
    },
    {
      key: 'funding-gaps',
      label: 'Funding gaps',
      value: null,
      state: 'unavailable',
      caption: 'Needs the planned reserve, which is being rebuilt on customer sell-through; no gap is computed yet.',
    },
    {
      key: 'evidence',
      label: 'Evidence outstanding',
      value: queueFigureState === 'ready' ? queueTotals.evidenceOutstanding : null,
      state: queueFigureState,
      tone: 'warning',
      caption:
        queueFigureState === 'empty'
          ? 'Could not be loaded. Click to retry.'
          : `Ended with no claim file applied${queueCaptionNote}`,
      onClick: queueFigureState === 'empty' ? retryQueue : () => setParam('stage', 'ended'),
    },
    {
      key: 'conflicts',
      label: 'Conflicting windows',
      value: clash?.kind === 'count' ? clash.count : null,
      // A calendar that is not set up is "not available", a different thing from a failed request.
      state: clashState === 'ready' && clash?.kind === 'unavailable' ? 'unavailable' : clashState,
      tone: 'warning',
      caption: clashError
        ? 'Could not be loaded. Click to retry.'
        : clash?.kind === 'unavailable'
          ? 'The customer calendar is not set up yet, so no clash count exists.'
          : 'Promotions overlapping a customer calendar event',
      onClick: clashError ? () => void refetchClash() : () => router.push('/promotions/timeline'),
    },
  ];
  const selectedRow: CporCaseListRow | null = useMemo(() => {
    if (selectedId == null) return null;
    const pools = [data?.items, proposedPage?.items, endedPage?.items];
    for (const pool of pools) {
      const hit = pool?.find((r) => r.id === selectedId);
      if (hit) return hit;
    }
    return null;
  }, [selectedId, data?.items, proposedPage?.items, endedPage?.items]);

  const inPlanningSupport = rowsAll
    .filter((r) => ['draft', 'proposed', 'approved', 'rejected'].includes(r.status))
    .reduce((n, r) => n + (Number(r.ttl_support_zar) || 0), 0);

  return (
    <Box data-testid="promotion-planner">
      <FundingChrome hideDomainHeader>
        <Stack spacing={2} sx={{ mt: 2 }}>
          {/* 1. Title, subtitle and the primary action */}
          <Stack
            data-testid="planner-header"
            direction={{ xs: 'column', md: 'row' }}
            spacing={1.5}
            alignItems={{ xs: 'flex-start', md: 'center' }}
            justifyContent="space-between"
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="h5" component="h1" sx={{ fontWeight: 600, lineHeight: 1.25 }}>
                Promotion planner
              </Typography>
              <Typography variant="body2" color="text.secondary" data-testid="planner-subtitle">
                Plan, approve and watch promotions by customer, from first draft to settlement.
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Tooltip title="Propose lines from the customer’s own sell-through (products, price, run rate); never other customers." arrow>
                <span>
                  <Button
                    size="small"
                    variant="contained"
                    startIcon={<AutoAwesomeOutlinedIcon />}
                    onClick={() => setProposeOpen(true)}
                    data-testid="planner-propose"
                  >
                    Create promotion plan
                  </Button>
                </span>
              </Tooltip>
              <Button size="small" variant="outlined" onClick={() => setCreateOpen(true)} data-testid="planner-new">
                New plan
              </Button>
              <Button size="small" variant="outlined" component={NextLink} href="/reports">
                Open in Reports
              </Button>
              <Button size="small" variant="outlined" component={NextLink} href="/admin/imports">
                Import claims / payments
              </Button>
            </Stack>
          </Stack>

          {/* 2. Exactly five KPI cards, in the mock-up order */}
          <Box
            data-testid="planner-kpi-strip"
            sx={{
              display: 'grid',
              gap: 1.5,
              gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(3, minmax(0, 1fr))', lg: 'repeat(5, minmax(0, 1fr))' },
            }}
          >
            <PlannerKpiCard
              testId="planner-kpi-planning"
              label="In planning"
              value={planningCount ?? '—'}
              unit="plans"
              state={countsState}
              caption="Draft, proposed, approved and rejected; replaced cases left out"
              onClick={baseCountsError ? () => void refetchBaseCounts() : () => setParam('stage', null)}
            />
            <PlannerKpiCard
              testId="planner-kpi-live"
              label="Live promotions"
              value={liveCount ?? '—'}
              unit="live"
              state={countsState}
              severity={countsState === 'ready' && (liveCount ?? 0) > 0 ? 'good' : 'neutral'}
              caption="Cases running now; replaced cases left out"
              onClick={baseCountsError ? () => void refetchBaseCounts() : () => setParam('stage', 'active')}
            />
            <PlannerKpiCard
              testId="planner-kpi-reserve"
              label="Planned reserve"
              state="unavailable"
              caption="Needs the planned reserve from customer sell-through price, cost and units, which is being rebuilt; no total is shown."
            />
            <PlannerKpiCard
              testId="planner-kpi-support"
              label="Actual support"
              state="unavailable"
              caption="Needs claims and payments tied to customer sell-through; no tenant-wide total exists yet."
            />
            <PlannerKpiCard
              testId="planner-kpi-at-risk"
              label="At-risk actions"
              value={queueFigureState === 'ready' ? queueTotals.total : '—'}
              unit="waiting"
              state={queueFigureState}
              severity={queueFigureState === 'ready' && queueTotals.total > 0 ? 'warn' : 'neutral'}
              caption={`Reapproval, awaiting approval and evidence outstanding${queueCaptionNote}`}
              onClick={
                queueFigureState === 'empty'
                  ? retryQueue
                  : () => document.getElementById('planner-action-queue')?.scrollIntoView?.({ behavior: 'smooth' })
              }
            />
          </Box>

          {/* Secondary row: the other cards this page already had */}
          <Box data-testid="planner-secondary-cards">
            <HeadlineStrip columns={6}>
          <HeadlineFigure
            label="Drafts to finish"
            value={draftsN ?? '—'}
            unit="plans"
            compact
            dense
            testId="planner-card-drafts"
            state={countsState}
            stateNote={baseCountsError ? 'Could not be loaded. Click to retry.' : undefined}
            caption={`${fmtCompact(inPlanningSupport)} support in draft / proposed / approved / rejected`}
            onClick={baseCountsError ? () => void refetchBaseCounts() : () => setParam('stage', 'draft')}
          />
          <HeadlineFigure
            label="Ended"
            value={endedN ?? '—'}
            unit="cases"
            compact
            dense
            testId="planner-card-ended"
            state={countsState}
            stateNote={baseCountsError ? 'Could not be loaded. Click to retry.' : undefined}
            caption="In the book — settle from the case desk, not from this strip"
            onClick={baseCountsError ? () => void refetchBaseCounts() : () => setParam('stage', 'ended')}
          />
          <HeadlineFigure
            label="Awaiting approval"
            value={awaitingN ?? '—'}
            unit="cases"
            compact
            dense
            testId="planner-card-awaiting"
            state={awaitingState}
            stateNote={awaitingError ? 'Could not be loaded. Click to retry.' : undefined}
            severity={awaitingState === 'ready' && (awaitingN ?? 0) > 0 ? 'warn' : 'neutral'}
            caption="Proposed cases waiting for a decision; replaced cases left out"
            onClick={awaitingError ? () => void refetchAwaiting() : () => setParam('stage', 'proposed')}
          />
          <HeadlineFigure
            label="Starting in 4 weeks"
            value={startingN ?? '—'}
            unit="campaigns"
            compact
            dense
            testId="planner-card-starting"
            state={startingState}
            stateNote={startingError ? 'Could not be loaded. Click to retry.' : undefined}
            caption={`Window starts ${startingReq.from} to ${startingReq.to}; replaced, cancelled and rejected left out`}
            onClick={
              startingError
                ? () => void refetchStarting()
                : () => setParams({ stage: null, window_from: startingReq.from, window_to: startingReq.to })
            }
          />
          <HeadlineFigure
            label="Unplanned aged stock"
            value={
              agedUnplanned.valued
                ? agedUnplanned.value != null
                  ? fmtCompact(agedUnplanned.value)
                  : '—'
                : fmtInt(agedUnplanned.units)
            }
            unit={agedUnplanned.valued ? undefined : 'units'}
            compact
            dense
            testId="planner-card-aged"
            state={aged.isLoading ? 'loading' : aged.isError ? 'empty' : 'ready'}
            stateNote={aged.isError ? 'Aged stock could not be loaded' : undefined}
            caption={agedStockCaption(agedUnplanned)}
            onClick={() => document.getElementById('planner-aged-stock')?.scrollIntoView?.({ behavior: 'smooth' })}
          />
          <HeadlineFigure
            label="Calendar clashes"
            value={clash?.kind === 'count' ? clash.count : '—'}
            unit={clash?.kind === 'count' ? 'clashes' : undefined}
            compact
            dense
            testId="planner-card-clashes"
            state={clashState === 'ready' && clash?.kind === 'unavailable' ? 'empty' : clashState}
            stateNote={
              clashError
                ? 'Could not be loaded. Click to retry.'
                : clash?.kind === 'unavailable'
                  ? 'Customer calendar is not set up yet (unavailable), so no clash count exists.'
                  : undefined
            }
            severity={clash?.kind === 'count' && clash.count > 0 ? 'warn' : 'neutral'}
            caption={
              clash?.kind === 'count'
                ? clash.count === 0
                  ? 'No open promotion overlaps a customer calendar event'
                  : `${clash.promotions} promotion${clash.promotions === 1 ? '' : 's'} across ${clash.customers} customer${
                      clash.customers === 1 ? '' : 's'
                    }, ending today or later. Open the timeline`
                : undefined
            }
            onClick={clashError ? () => void refetchClash() : () => router.push('/promotions/timeline')}
          />
            </HeadlineStrip>
          </Box>

          {/* 3. Filter bar: Customer, Status, date range, Distributor, Product */}
          <Box data-testid="planner-filter-bar">
            <ScopeBar
              chips={[
                ...LIFECYCLE_STAGES.map((s) => ({
                  key: s,
                  label: `${STAGE_LABEL[s]} · ${counts[s] ?? 0}`,
                  active: stageFilter === s,
                  onToggle: () => setParam('stage', stageFilter === s ? null : s),
                  tone: (s === 'active' ? 'success' : s === 'proposed' ? 'warning' : 'default') as
                    | 'success'
                    | 'warning'
                    | 'default',
                })),
                {
                  key: 'test_data',
                  label: `Test data · ${data?.test_data_count ?? 0}`,
                  active: testDataOnly,
                  onToggle: () => setParam('test_data', testDataOnly ? null : 'only'),
                  tone: 'warning' as const,
                },
              ]}
              summary={
                testDataOnly
                  ? `${rows.length} test-data cases · commercial book ${bookN} · ${planningN} in planning`
                  : caseScopeIsActive(scope)
                    ? `${rows.length} matching${stageFilter ? ` ${STAGE_LABEL[stageFilter]}` : ''} · ${bookN} in the book · ${planningN} in planning`
                    : stageFilter
                      ? `${rows.length} of ${counts[stageFilter] ?? 0} ${STAGE_LABEL[stageFilter]} cases · ${bookN} in the book · ${planningN} in planning`
                      : `${rows.length} of ${bookN} cases (all stages) · ${planningN} in planning`
              }
              onClear={() => setParams({ stage: null, test_data: null, ...caseScopeClearPatch() })}
              clearAvailable={caseScopeIsActive(scope) || testDataOnly}
              filters={
                <CaseScopeFilters
                  scope={scope}
                  onPatch={setParams}
                  stage={stageFilter}
                  onStageChange={(next) => setParam('stage', next)}
                />
              }
            />
          </Box>

          {/* 4. Timeline by customer (full width); promotion detail opens in a drawer when a case is selected */}
          <Box data-testid="planner-timeline-section" sx={{ minWidth: 0 }}>
            <Stack spacing={2}>
              <CustomerRowsTimeline
                cases={rows}
                today={today}
                selectedId={selectedId}
                onSelect={setSelectedId}
                status={isLoading ? 'loading' : isError ? 'error' : 'ready'}
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
                  {rows.map((p) => {
                    const support = formatDualMoneyLine(p.ttl_support_zar, {
                      currencyCode: p.currency_code,
                      roeSnapshot: p.roe_snapshot,
                      missingRoe: Boolean(p.missing_roe) || p.fx_booked === false,
                    });
                    return (
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
                              Support <b>{support.local}</b>
                              {' · '}
                              {support.usdLine}
                            </Typography>
                          </Stack>
                        </CardContent>
                      </CardActionArea>
                    </Card>
                    );
                  })}
                </Stack>
              ) : (
                <PlanGrid rows={rows} onOpen={setSelectedId} />
              )}
            </ModuleDataSection>
            </Stack>
          </Box>

          <Drawer
            anchor={isMobile ? 'bottom' : 'right'}
            open={detailOpen}
            onClose={closeDetail}
            keepMounted={false}
            data-testid="planner-detail-drawer"
            slotProps={{
              paper: {
                sx: {
                  width: isMobile ? '100%' : 'min(440px, 92vw)',
                  maxHeight: isMobile ? '92vh' : undefined,
                },
              },
            }}
          >
            <Stack sx={{ p: 2, height: '100%', minHeight: 0 }} spacing={1}>
              <Stack direction="row" alignItems="flex-start" justifyContent="flex-end">
                <IconButton
                  aria-label="Close promotion detail"
                  onClick={closeDetail}
                  data-testid="planner-detail-close"
                >
                  <CloseIcon />
                </IconButton>
              </Stack>
              <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
                <PlannerDetailPanel
                  row={selectedRow}
                  unavailableId={selectedId != null && !selectedRow ? selectedId : null}
                  actions={
                    selectedRow && queueFigureState === 'ready' && !queueIncomplete
                      ? queue.filter((a) => a.caseId === selectedRow.id)
                      : undefined
                  }
                  onOpen={onOpen}
                  onClear={closeDetail}
                />
              </Box>
            </Stack>
          </Drawer>

          {/* 5. Action queue */}
          <PlannerQueueSection
            cards={queueCards}
            items={queue}
            loading={queueLoading}
            unavailable={queueUnavailable}
            incomplete={queueIncomplete}
            onRetry={retryQueue}
            onSelect={setSelectedId}
          />
          <Typography variant="caption" color="text.secondary" sx={{ px: 0.5 }}>
            The queue does not flag a live listing that is off the promo price. Listing, competitor price and
            observed cover are on the Evidence column when you create a promotion plan.
          </Typography>

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

          <Box
            sx={{
              display: 'grid',
              gap: 2,
              gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'repeat(2, minmax(0, 1fr))' },
              alignItems: 'start',
            }}
          >
            <Box id="planner-aged-stock">
              <Panel title="Aged and slow stock" subtitle="One draft per customer, or one action on a line" flush>
                <AgedStockPanel onOpen={onOpen} />
              </Panel>
            </Box>
            <CapabilityLedger items={PLANNER_CAPABILITIES} />
          </Box>
        </Stack>

      <Dialog
        open={proposeOpen}
        onClose={() => {
          setProposeOpen(false);
          if (proposeRequested) setParam('propose', null);
        }}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>Create promotion plan</DialogTitle>
        <DialogContent>
          <PromoPlanBuilderPanel />
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setProposeOpen(false);
              if (proposeRequested) setParam('propose', null);
            }}
          >
            Close
          </Button>
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
          void invalidateClashSummary(qc);
          onOpen(id);
        }}
        onError={(m) => setToast(m)}
      />
      <Snackbar open={!!toast} autoHideDuration={4000} onClose={() => setToast(null)} message={toast} />
      </FundingChrome>
    </Box>
  );
}

/** Words for the aged-stock card. The value is the API's (units x the customer's reported cost, ex-VAT). */
function agedStockCaption(a: ReturnType<typeof unplannedAgedStock>): string {
  const lines = `${a.lineCount} slow or unsold line${a.lineCount === 1 ? '' : 's'} with no open action`;
  const capped = a.truncated ? ' (list capped, so at least this many)' : '';
  if (!a.valued) return `${lines}${capped}. Units on hand; the API returned no money value.`;
  const n = a.linesWithoutCost;
  const noCost =
    n === 0
      ? 'Every line has a cost.'
      : `${n} line${n === 1 ? ' has' : 's have'} no cost and ${n === 1 ? 'is' : 'are'} not valued (${fmtInt(a.unitsWithoutCost)} units).`;
  const empty = a.value == null && n > 0 && a.linesWithCost === 0 ? ' No line has a cost, so there is no value.' : '';
  return `${fmtInt(a.units)} units on ${lines}${capped}. ${noCost}${empty} Cost: customer-reported unit MAC, else unit cost, ex-VAT.`;
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
        width: 180,
        wrapText: true,
        autoHeight: true,
        valueFormatter: (p) => {
          const dual = formatDualMoneyLine(p.value as number | null, {
            currencyCode: p.data?.currency_code,
            roeSnapshot: p.data?.roe_snapshot,
            missingRoe: Boolean(p.data?.missing_roe) || p.data?.fx_booked === false,
          });
          return `${dual.local} · ${dual.usdLine}`;
        },
      },
      {
        colId: 'on_shelf',
        headerName: 'On shelf',
        width: 110,
        valueGetter: () => null,
        valueFormatter: () => '—',
        tooltipValueGetter: () =>
          'Listing, competitor price, and observed cover are on the Evidence column when you create a promotion plan. This case list does not repeat them.',
      },
      {
        colId: 'export_template',
        headerName: 'Export template',
        minWidth: 160,
        flex: 1,
        valueGetter: () => null,
        valueFormatter: () => '—',
        tooltipValueGetter: () =>
          'Export writes the plan in the stored column layout. The fixed workbook route is unchanged.',
      },
      {
        field: 'flags',
        headerName: 'Flags',
        minWidth: 180,
        flex: 1.2,
        valueFormatter: (p) => ((p.value as string[]) ?? []).join(' · ') || '—',
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
  const [fxRate, setFxRate] = useState('');
  const { data: types } = useQuery({
    queryKey: ['cpor', 'promotion-types'],
    queryFn: ({ signal }) => apiGet<PromoTypes>('/api/v1/cpor/meta/promotion-types', { signal }),
    enabled: open,
  });
  const { data: fxToday } = useQuery({
    queryKey: ['cpor', 'fx', 'today'],
    queryFn: ({ signal }) =>
      apiGet<{
        rate: number | null;
        source: string;
        is_fallback: boolean;
        fetch_failed: boolean;
        rate_date: string | null;
      }>('/api/v1/cpor/fx/rates/today', { signal }),
    enabled: open,
  });
  useEffect(() => {
    if (!open) return;
    if (fxToday?.fetch_failed) {
      setFxRate('');
      return;
    }
    if (fxToday?.rate != null) setFxRate(String(fxToday.rate));
  }, [open, fxToday?.rate, fxToday?.fetch_failed]);
  const create = useMutation({
    mutationFn: () =>
      apiPost<{ id: number }>('/api/v1/cpor/cases', {
        customer_id: cust!.id,
        promotion_type: promoType,
        window_start: windowStart,
        window_end: windowEnd,
        fx_mode: 'booked',
        fx_proposed_rate: fxRate.trim() ? Number(fxRate) : null,
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
          <TextField
            size="small"
            type="number"
            label="Suggested ZAR per USD"
            value={fxRate}
            onChange={(e) => setFxRate(e.target.value)}
            fullWidth
            helperText={
              fxToday?.fetch_failed
                ? 'Fetch failed — this case will be created unbooked and flagged. A typed rate is an operator book, not a silent substitute.'
                : `This rate books at creation and does not move later.${fxToday?.rate_date ? ` Source date ${fxToday.rate_date}.` : ''}`
            }
            inputProps={{ 'data-testid': 'create-case-fx-rate', step: '0.01' }}
          />
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
