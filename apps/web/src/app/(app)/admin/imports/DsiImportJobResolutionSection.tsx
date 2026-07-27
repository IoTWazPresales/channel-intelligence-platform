'use client';

import NextLink from 'next/link';
import Link from '@mui/material/Link';
import {
  Alert,
  Box,
  Button,
  Divider,
  Drawer,
  Stack,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { BulkSelectionToolbar, type BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';

import type { PlanApplyFeedback } from '@/app/(app)/admin/imports/dsi/dsiSteward.types';
import {
  StewardCandidatesPagination,
  StewardPendingButton,
  StewardEntityTabsBar,
  StewardResolutionPlanToolbar,
  StewardCandidateFilters,
  ImportStewardCandidateWorkspace,
  StewardWorkspaceViewportShell,
  StewardBulkActionInlineForm,
  StewardBulkSection,
  StewardCandidateDrawer,
  computeImportStewardSelectionHeaderState,
  formatPlanActionLabel,
  useStewardBulkSteward,
  PlanDialogRowDetail,
} from '@/features/import-steward';
import {
  defaultDsiStewardCandidateFilterState,
  filterDsiStewardCandidates,
  paginateDsiStewardCandidateRows,
  type DsiStewardCandidateFilterState,
} from '@/app/(app)/admin/imports/dsi';
import {
  DsiMappingStewardPanel,
  DsiProductCandidateExportToolbar,
  DsiCountryRegionFallback,
  DsiRegionChannelTabPanel,
  isDsiEntityCandidateTab,
  DsiStewardLoadingCallout,
  DSI_STEWARD_CONFIG,
  DSI_ENGINE_CONFIG,
  DSI_ENTITY_TABS,
  useDsiCandidatesPage,
  useDsiEntityTabCounts,
  defaultDsiStewardFiltersForTab,
  dsiStewardFiltersMatchTabDefault,
  dsiTabDependencyNudge,
  formatDsiEntityTabLabel,
  useDsiResolutionPlan,
  type DsiBulkAction,
  type DsiCandidateRow,
  type DsiEntityTabId,
  type DsiRegionEvidenceDto,
} from '@/app/(app)/admin/imports/dsi';
import { DsiCustomerSearchFields } from '@/app/(app)/admin/imports/dsi/DsiCustomerSearchFields';
import { useDsiStewardBulkBusy } from '@/app/(app)/admin/imports/dsi/useDsiStewardBulkBusy';
import { safeDisplayError } from '@/lib/api';

import {
  buildDuplicateClusterIndex,
  duplicateClusterMembersForKey,
} from '@/app/(app)/admin/imports/dsi/dsiDuplicateCluster';

import { buildDsiResolutionWorkspaceColumns } from './dsi/dsiResolutionWorkspaceTableProps';
import type { DistributorSiSummary } from './dsiStepUtils';
import {
  dsiDataQualityBlockingRows,
  dsiStewardMapBlockingRows,
} from './dsiStepUtils';

export function DsiImportJobResolutionSection({
  importJobId,
  candidates: candidatesOverride,
  candidatesLoading: candidatesLoadingOverride,
  candidatesError: candidatesErrorOverride,
  onInvalidate,
  dsiPipelineRunning = false,
  onAsyncPipelineStarted,
  validateSummary = null,
}: {
  importJobId: number;
  /** Test / story override — skips paginated fetch when provided. */
  candidates?: DsiCandidateRow[];
  candidatesLoading?: boolean;
  candidatesError?: unknown;
  onInvalidate: () => void;
  /** True while validate/revalidate Celery pipeline is in flight (imports page). */
  dsiPipelineRunning?: boolean;
  onAsyncPipelineStarted?: (args: { importJobId: number; taskId?: string | null }) => void;
  /** Latest distributor_si_summary for blocker empty-state copy. */
  validateSummary?: DistributorSiSummary | null;
}) {
  const tabbedMode = candidatesOverride == null;

  const [activeTab, setActiveTab] = useState<DsiEntityTabId>('distributor');
  const [visitedTabs, setVisitedTabs] = useState<Set<DsiEntityTabId>>(() => new Set(['distributor']));
  const [filtersByTab, setFiltersByTab] = useState<Record<DsiEntityTabId, DsiStewardCandidateFilterState>>(() => ({
    distributor: defaultDsiStewardFiltersForTab('distributor'),
    customer: defaultDsiStewardFiltersForTab('customer'),
    product: defaultDsiStewardFiltersForTab('product'),
    region_channel: defaultDsiStewardFiltersForTab('region_channel'),
  }));

  const [detailCandidate, setDetailCandidate] = useState<DsiCandidateRow | null>(null);
  const [rowActionPendingId, setRowActionPendingId] = useState<number | null>(null);
  const [candidateFilters, setCandidateFilters] = useState<DsiStewardCandidateFilterState>(
    defaultDsiStewardCandidateFilterState
  );
  const [bulkMode, setBulkMode] = useState<BulkTableSelectionMode>('normal');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [planApplySummary, setPlanApplySummary] = useState<PlanApplyFeedback | null>(null);
  const selectionAnchorIdRef = useRef<number | null>(null);
  const workspaceToolbarRef = useRef<HTMLDivElement | null>(null);

  const focusWorkspaceToolbar = useCallback(() => {
    const el = workspaceToolbarRef.current?.querySelector<HTMLElement>(
      'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
    );
    el?.focus();
  }, []);

  const activeFilters = tabbedMode ? filtersByTab[activeTab] : candidateFilters;
  const setActiveFilters = useCallback(
    (next: DsiStewardCandidateFilterState) => {
      if (tabbedMode) {
        setFiltersByTab((prev) => ({ ...prev, [activeTab]: next }));
      } else {
        setCandidateFilters(next);
      }
    },
    [activeTab, tabbedMode]
  );

  const { counts: tabCounts, openByTab, productMatchStatusCounts } = useDsiEntityTabCounts(
    importJobId,
    tabbedMode
  );

  const isCandidateTab = isDsiEntityCandidateTab(activeTab);

  const candidatesPage = useDsiCandidatesPage(importJobId, activeFilters, {
    enabled: tabbedMode && visitedTabs.has(activeTab) && isCandidateTab,
    tabKey: activeTab,
  });

  const candidates = candidatesOverride ?? candidatesPage.candidates;
  const candidatesLoading =
    candidatesLoadingOverride ??
    (candidatesPage.query.isLoading ||
      (candidatesPage.query.isFetching && candidatesPage.candidates.length === 0));
  const candidatesError =
    candidatesErrorOverride ?? (candidatesPage.query.isError ? candidatesPage.query.error : null);
  const candidatesTotal = candidatesOverride != null ? candidates.length : candidatesPage.total;

  useEffect(() => {
    setSelectedIds([]);
    setDetailCandidate(null);
    selectionAnchorIdRef.current = null;
  }, [
    candidatesOverride,
    activeTab,
    candidatesPage.page,
    candidatesPage.pageSize,
    candidatesPage.skip,
  ]);

  const plan = useDsiResolutionPlan({
    importJobId,
    candidates,
    onInvalidate,
    onAsyncPipelineStarted,
    setSelectedIds,
    setPlanApplySummary,
  });

  const stewardBulk = useDsiStewardBulkBusy(importJobId);

  const planComputeBlocking =
    (plan.suggestionsQuery.isFetching && !plan.suggestionsQuery.data) ||
    (stewardBulk.computeActive && !plan.applyResolutionPlan.isPending);

  const planApplyBlocked =
    planComputeBlocking ||
    stewardBulk.applyActive ||
    plan.refreshPlanEffective.isPending;

  const bulk = useStewardBulkSteward({
    importJobId,
    selectedIds,
    setSelectedIds,
    setBulkMode,
    onInvalidate,
    onBulkClosed: focusWorkspaceToolbar,
    onPlanRefresh: () => plan.refreshSuggestions(),
    onEvictResolvedCandidates: plan.evictResolvedCandidates,
    onShrinkPlanScope: plan.shrinkPlanScope,
    onApplyPlanFallback: async ({ action, regionId, channelId }) => {
      if (action === 'set_plan_fallback_channel') {
        plan.setPlanChannelId(channelId);
        await plan.suggestionsQuery.refetch();
      }
    },
    applySuggestedRegion: async ({ candidateIds }) => {
      for (const id of candidateIds) {
        const row = plan.planByCandidateId.get(id);
        const ev = row?.region_evidence as DsiRegionEvidenceDto | undefined;
        const rid = ev?.suggested_region_id;
        if (rid != null && Number.isFinite(Number(rid))) {
          plan.patchPlanOverride(id, { region_id: Number(rid) });
        }
      }
      await plan.refreshPlanEffective.mutateAsync({
        overrides: plan.overridesPayload(),
        globalSuspicious: plan.planGlobalSuspicious,
      });
    },
    config: DSI_ENGINE_CONFIG,
  });

  const closeBulkForm = useCallback(() => {
    setBulkMode('normal');
    setSelectedIds([]);
    bulk.setPreviewOpen(false);
    focusWorkspaceToolbar();
  }, [bulk, focusWorkspaceToolbar]);

  const filteredCandidates = useMemo(
    () => filterDsiStewardCandidates(candidates, activeFilters, plan.planByCandidateId),
    [candidates, activeFilters, plan.planByCandidateId]
  );

  const clientQueueFilterActive = tabbedMode && candidatesPage.clientQueueFilterActive;

  const filteredPageCount = Math.max(
    1,
    Math.ceil(filteredCandidates.length / Math.max(1, candidatesPage.pageSize))
  );

  const gridCandidates = useMemo(() => {
    if (!clientQueueFilterActive) return filteredCandidates;
    return paginateDsiStewardCandidateRows(
      filteredCandidates,
      candidatesPage.page,
      candidatesPage.pageSize
    );
  }, [
    filteredCandidates,
    clientQueueFilterActive,
    candidatesPage.page,
    candidatesPage.pageSize,
  ]);

  useEffect(() => {
    if (!clientQueueFilterActive || candidatesPage.query.isFetching) return;
    if (candidatesPage.page > 0 && candidatesPage.page >= filteredPageCount) {
      candidatesPage.setPage(Math.max(0, filteredPageCount - 1));
    }
  }, [
    clientQueueFilterActive,
    candidatesPage.page,
    candidatesPage.setPage,
    candidatesPage.query.isFetching,
    filteredPageCount,
  ]);

  const displayedCandidates = gridCandidates;

  const openBulkWorkflow = useCallback(
    (action: DsiBulkAction) => {
      bulk.setBulkAction(action);
      setBulkMode('selecting');
      if (selectedIds.length === 0 && displayedCandidates.length > 0) {
        setSelectedIds(displayedCandidates.map((c) => c.id));
      }
    },
    [bulk, displayedCandidates, selectedIds.length]
  );

  const selectedReadyPlanIds = useMemo(() => {
    const ready = new Set(plan.readyPlanCandidateIds);
    return selectedIds.filter((id) => ready.has(id));
  }, [selectedIds, plan.readyPlanCandidateIds]);

  const supervisedAutoResolvedRows = useMemo(() => {
    const raw = plan.resolutionPlan?.rows;
    if (!Array.isArray(raw)) return [] as Array<Record<string, unknown>>;
    return raw.filter((row) => {
      const r = row as Record<string, unknown>;
      return r.auto_resolved_supervised === true;
    }) as Array<Record<string, unknown>>;
  }, [plan.resolutionPlan]);

  const selectVisibleReadyInGrid = useCallback(() => {
    setSelectedIds(
      displayedCandidates
        .filter((c) => plan.planByCandidateId.get(c.id)?.ready === true)
        .map((c) => c.id)
    );
  }, [displayedCandidates, plan.planByCandidateId]);

  const candidatesById = useMemo(() => {
    const m: Record<number, DsiCandidateRow> = {};
    for (const c of candidates) m[c.id] = c;
    return m;
  }, [candidates]);

  const openStewardDrawer = useCallback((row: DsiCandidateRow) => {
    setDetailCandidate(row);
  }, []);

  const isDsiRowTerminal = useCallback(
    (row: DsiCandidateRow) => DSI_STEWARD_CONFIG.terminalStatuses.has((row.status || '').trim()),
    []
  );

  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const workspaceVisibleRowIds = useMemo(() => displayedCandidates.map((c) => c.id), [displayedCandidates]);
  const workspaceHeaderState = useMemo(
    () => computeImportStewardSelectionHeaderState(workspaceVisibleRowIds, selectedIdSet),
    [workspaceVisibleRowIds, selectedIdSet]
  );

  const onWorkspaceToggleRowSelection = useCallback(
    (rowId: number, event?: MouseEvent) => {
      const visibleIds = workspaceVisibleRowIds;
      if (event?.shiftKey && selectionAnchorIdRef.current != null) {
        const anchorId = selectionAnchorIdRef.current;
        const i0 = visibleIds.indexOf(anchorId);
        const i1 = visibleIds.indexOf(rowId);
        if (i0 >= 0 && i1 >= 0) {
          const [lo, hi] = i0 < i1 ? [i0, i1] : [i1, i0];
          const rangeIds = visibleIds.slice(lo, hi + 1);
          setSelectedIds((prev) => Array.from(new Set([...prev, ...rangeIds])));
          selectionAnchorIdRef.current = rowId;
          return;
        }
      }
      setSelectedIds((prev) => (prev.includes(rowId) ? prev.filter((x) => x !== rowId) : [...prev, rowId]));
      selectionAnchorIdRef.current = rowId;
    },
    [workspaceVisibleRowIds]
  );

  const onWorkspaceToggleAllVisibleSelection = useCallback(() => {
    setSelectedIds((prev) => {
      const prevSet = new Set(prev);
      const allVisibleSelected =
        workspaceVisibleRowIds.length > 0 && workspaceVisibleRowIds.every((id) => prevSet.has(id));
      if (allVisibleSelected) {
        return prev.filter((id) => !workspaceVisibleRowIds.includes(id));
      }
      return Array.from(new Set([...prev, ...workspaceVisibleRowIds]));
    });
  }, [workspaceVisibleRowIds]);

  const workspaceSelection = useMemo(
    () => ({
      selectedIds: selectedIdSet,
      onToggle: onWorkspaceToggleRowSelection,
      onToggleAllVisible: onWorkspaceToggleAllVisibleSelection,
      visibleRowIds: workspaceVisibleRowIds,
      headerState: workspaceHeaderState,
    }),
    [
      selectedIdSet,
      onWorkspaceToggleRowSelection,
      onWorkspaceToggleAllVisibleSelection,
      workspaceVisibleRowIds,
      workspaceHeaderState,
    ]
  );

  const onTabChange = useCallback((tab: DsiEntityTabId) => {
    setVisitedTabs((prev) => {
      if (prev.has(tab)) return prev;
      const next = new Set(prev);
      next.add(tab);
      return next;
    });
    setActiveTab(tab);
  }, []);

  const dependencyNudge = tabbedMode
    ? dsiTabDependencyNudge(activeTab, openByTab, openByTab.region_channel)
    : null;

  const revalidatePipelineBusy =
    dsiPipelineRunning || plan.dsiRevalidateFromServer.isPending;

  const stewardOverlayBusy =
    bulk.bulkPreview.isPending ||
    bulk.bulkApply.isPending ||
    plan.applyResolutionPlan.isPending ||
    plan.refreshPlanEffective.isPending ||
    planComputeBlocking ||
    (stewardBulk.applyActive && !plan.applyResolutionPlan.isPending) ||
    revalidatePipelineBusy;

  const stewardBusyMessage = useMemo(() => {
    if (bulk.bulkApply.isPending) return 'Applying bulk steward actions…';
    if (bulk.bulkPreview.isPending) return 'Building bulk steward preview…';
    if (plan.applyResolutionPlan.isPending || stewardBulk.applyActive) {
      return 'Applying resolution plan… Large batches can take 10+ minutes — you can keep working; progress appears in the activity bell.';
    }
    if (planComputeBlocking) {
      return 'Computing resolution plan… Apply is disabled until compute finishes.';
    }
    if (plan.refreshPlanEffective.isPending) return 'Updating resolution plan after your edits…';
    if (revalidatePipelineBusy) return 'Re-running import validation on the server…';
    return undefined;
  }, [
    bulk.bulkApply.isPending,
    bulk.bulkPreview.isPending,
    plan.applyResolutionPlan.isPending,
    stewardBulk.applyActive,
    planComputeBlocking,
    plan.refreshPlanEffective.isPending,
    revalidatePipelineBusy,
  ]);

  const planInitialLoading =
    candidates.length > 0 &&
    plan.suggestionsQuery.fetchStatus === 'fetching' &&
    !plan.suggestionsQuery.data;

  const isRegionChannelTab = activeTab === 'region_channel';

  /** Keep table shell whenever the job workspace is shown so chips + empty state stay aligned. */
  const keepTableWhenFilterEmpty =
    importJobId != null && !candidatesLoading && isCandidateTab;

  const effectiveDetailCandidate = useMemo(() => {
    if (detailCandidate == null) return null;
    return candidates.find((c) => c.id === detailCandidate.id) ?? detailCandidate;
  }, [detailCandidate, candidates]);

  const duplicateClusterIndex = useMemo(() => buildDuplicateClusterIndex(candidates), [candidates]);

  const customerNormalizedKeysOnPage = useMemo(
    () =>
      candidates
        .filter((c) => c.entity_type === 'customer_dealer_token')
        .map((c) => c.normalized_key)
        .filter(Boolean),
    [candidates]
  );

  const duplicateClusterMembersForSelection = useMemo(() => {
    if (!effectiveDetailCandidate) return [];
    return [
      ...duplicateClusterMembersForKey(
        duplicateClusterIndex,
        effectiveDetailCandidate.normalized_key
      ),
    ];
  }, [duplicateClusterIndex, effectiveDetailCandidate]);

  useEffect(() => {
    if (rowActionPendingId == null) return;
    const row = candidates.find((c) => c.id === rowActionPendingId);
    if (row && DSI_STEWARD_CONFIG.terminalStatuses.has((row.status || '').trim())) {
      setRowActionPendingId(null);
    }
  }, [candidates, rowActionPendingId]);

  const workspaceColumns = useMemo(
    () =>
      buildDsiResolutionWorkspaceColumns({
        planByCandidateId: plan.planByCandidateId,
        formatPlanActionLabel,
        isTerminal: isDsiRowTerminal,
        onFocusRow: openStewardDrawer,
        onOpenPlanDrawer: (id) => plan.handleOpenSuggestionRow(id),
        rowActionPendingId,
        jobId: importJobId,
      }),
    [
      plan.planByCandidateId,
      isDsiRowTerminal,
      openStewardDrawer,
      plan.handleOpenSuggestionRow,
      rowActionPendingId,
      importJobId,
    ]
  );

  const refreshResolutionPlanEffective = useCallback(async () => {
    if (plan.planLoadToken === 0) return;
    await plan.refreshPlanEffective.mutateAsync({
      overrides: plan.overridesPayload(),
      globalSuspicious: plan.planGlobalSuspicious,
    });
  }, [plan]);

  const lookupPeerCandidateByNormalizedKey = useCallback(
    (normalizedKey: string) =>
      candidates.find(
        (c) =>
          c.entity_type === 'customer_dealer_token' && c.normalized_key === normalizedKey
      ) ?? null,
    [candidates]
  );

  const openPeerCandidateByNormalizedKey = useCallback(
    (normalizedKey: string) => {
      const peer = lookupPeerCandidateByNormalizedKey(normalizedKey);
      if (peer) setDetailCandidate(peer);
    },
    [lookupPeerCandidateByNormalizedKey]
  );

  const openActionableCandidates = useMemo(
    () => candidates.filter((c) => !DSI_STEWARD_CONFIG.terminalStatuses.has((c.status || '').trim())),
    [candidates]
  );
  const masterMergeExcluded = validateSummary?.master_merge_excluded_rows ?? 0;
  const stewardMapBlockers = dsiStewardMapBlockingRows(validateSummary);
  const dataQualityBlockers = dsiDataQualityBlockingRows(validateSummary);
  const showBlockerEmptyState =
    !candidatesLoading &&
    (stewardMapBlockers > 0 || dataQualityBlockers > 0 || masterMergeExcluded > 0) &&
    openActionableCandidates.length === 0;

  const candidateWorkspace = (
    <ImportStewardCandidateWorkspace<DsiCandidateRow>
      embedded
      keepTableWhenFilterEmpty={keepTableWhenFilterEmpty}
      rootTestId="dsi-resolution-candidate-grid"
      listDomainId={DSI_STEWARD_CONFIG.listDomainId}
      importJobId={importJobId}
      copy={DSI_STEWARD_CONFIG.listShellCopy}
      openRows={isRegionChannelTab ? [] : candidates}
      filteredRows={isRegionChannelTab ? [] : displayedCandidates}
      busy={stewardOverlayBusy}
      busyOverlay={stewardBusyMessage ? { message: stewardBusyMessage } : null}
      columns={workspaceColumns}
      selection={workspaceSelection}
      tabsSlot={
        tabbedMode ? (
          <Stack spacing={1}>
            <StewardEntityTabsBar
              tabs={DSI_ENTITY_TABS}
              activeTab={activeTab}
              onChange={onTabChange}
              counts={tabCounts}
              busy={stewardOverlayBusy}
              testIdPrefix="dsi"
              ariaLabel="DSI entity resolution"
              formatTabAriaLabel={formatDsiEntityTabLabel}
            />
            {dependencyNudge ? (
              <Alert severity="warning" variant="outlined" data-testid="dsi-tab-dependency-nudge">
                {dependencyNudge}
              </Alert>
            ) : null}
          </Stack>
        ) : undefined
      }
      filtersSlot={
        isRegionChannelTab ? null : (
          <StewardCandidateFilters
            filters={activeFilters}
            onChange={setActiveFilters}
            visibleCount={
              clientQueueFilterActive ? filteredCandidates.length : displayedCandidates.length
            }
            totalCount={tabbedMode ? candidatesPage.total : Math.max(candidatesTotal, candidates.length)}
            hideEntityFilter={tabbedMode}
            hidePartyFilter={tabbedMode && activeTab !== 'distributor'}
            showProductMatchStatusChips={tabbedMode && activeTab === 'product'}
            productMatchStatusCounts={
              tabbedMode && activeTab === 'product' ? productMatchStatusCounts : undefined
            }
            clearToDefault={
              tabbedMode ? () => defaultDsiStewardFiltersForTab(activeTab) : undefined
            }
            isAtDefault={
              tabbedMode
                ? (filters) => dsiStewardFiltersMatchTabDefault(filters, activeTab)
                : undefined
            }
          />
        )
      }
      mainContentSlot={
        isRegionChannelTab ? (
          <DsiRegionChannelTabPanel
            importJobId={importJobId}
            unresolvedGeoQuery={plan.unresolvedGeoQuery}
            catalogChannels={plan.channels}
            catalogRegions={plan.regions}
            onInvalidate={plan.invalidateGeoAndPlan}
          />
        ) : undefined
      }
      isLoading={isRegionChannelTab ? plan.unresolvedGeoQuery.isLoading : candidatesLoading}
      toolbarSlot={
        <Stack ref={workspaceToolbarRef} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            {bulkMode === 'selecting' ? (
              <BulkSelectionToolbar
                mode={bulkMode}
                selectedCount={selectedIds.length}
                visibleRowCount={displayedCandidates.length}
                onEnterSelectionMode={() => setBulkMode('selecting')}
                onExitSelectionMode={closeBulkForm}
                onSelectAllVisible={() => setSelectedIds(displayedCandidates.map((c) => c.id))}
                onDeselectAll={() => setSelectedIds([])}
                busy={
                  bulk.bulkPreview.isPending ||
                  bulk.bulkApply.isPending ||
                  plan.applyResolutionPlan.isPending ||
                  plan.refreshPlanEffective.isPending
                }
                previewDangerLabel="Preview bulk steward"
                previewDangerDisabled={
                  selectedIds.length === 0 || bulk.bulkPreview.isPending || !bulk.bulkFormReady
                }
                onPreviewDangerAction={() => void bulk.bulkPreview.mutateAsync()}
              />
            ) : isRegionChannelTab ? (
              <>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => openBulkWorkflow('set_plan_fallback_channel')}
                  data-testid="dsi-bulk-channel-open"
                >
                  Plan fallback channel…
                </Button>
                <Typography variant="caption" color="text.secondary">
                  Plan fallbacks below — use bulk Register ISO regions for geographic channel tokens.
                </Typography>
              </>
            ) : (
              <>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={displayedCandidates.length === 0 && selectedIds.length === 0}
                  onClick={() => openBulkWorkflow('map_customer')}
                  data-testid="dsi-bulk-map-open"
                >
                  Bulk map…
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={displayedCandidates.length === 0 && selectedIds.length === 0}
                  onClick={() => openBulkWorkflow('create_provisional_customer')}
                  data-testid="dsi-bulk-provisional-open"
                >
                  Bulk provisional…
                </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() => openBulkWorkflow('apply_suggested_region')}
              disabled={selectedIds.length === 0}
              data-testid="dsi-bulk-apply-suggested-region"
            >
              Apply suggested region…
            </Button>
              </>
            )}
            {tabbedMode && activeTab === 'product' && bulkMode !== 'selecting' && !isRegionChannelTab ? (
              <DsiProductCandidateExportToolbar candidates={displayedCandidates} />
            ) : null}
            {activeTab === 'customer' && bulkMode !== 'selecting' ? (
              <DsiCountryRegionFallback
                importJobId={importJobId}
                enabled={plan.planRegionFallbackEnabled}
                onEnabledChange={plan.setPlanRegionFallbackEnabled}
                onRegionIdChange={plan.setPlanRegionId}
                disabled={stewardOverlayBusy}
                catalogRegions={plan.regions}
              />
            ) : null}
            {!isRegionChannelTab ? (
              <>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!displayedCandidates.some((c) => plan.planByCandidateId.get(c.id)?.ready === true)}
                  onClick={selectVisibleReadyInGrid}
                  data-testid="dsi-plan-select-visible-ready"
                >
                  Select visible ready
                </Button>
                <Typography variant="caption" color="text.secondary">
                  {selectedIds.length} selected · Ready {plan.readyPlanCandidateIds.length}
                </Typography>
                <Box sx={{ flexGrow: 1 }} />
                <StewardPendingButton
                  variant="outlined"
                  size="small"
                  pending={plan.applyResolutionPlan.isPending}
                  pendingLabel="Applying…"
                  disabled={
                    selectedReadyPlanIds.length === 0 ||
                    planApplyBlocked ||
                    (stewardOverlayBusy && !plan.applyResolutionPlan.isPending)
                  }
                  onClick={() =>
                    void plan.applyResolutionPlan.mutateAsync(selectedReadyPlanIds).catch(() => {})
                  }
                  data-testid="dsi-resolution-plan-apply-selected"
                >
                  Apply selected ready ({selectedReadyPlanIds.length})
                </StewardPendingButton>
              </>
            ) : (
              <Box sx={{ flexGrow: 1 }} />
            )}
          </Stack>
      }
      bulkFormSlot={
        bulkMode === 'selecting' ? (
          <StewardBulkActionInlineForm
            bulk={bulk}
            regions={plan.regions}
            channels={plan.channels}
            onCancel={closeBulkForm}
            testIds={DSI_ENGINE_CONFIG.bulkTestIds}
            renderMapCustomerFields={(args) => <DsiCustomerSearchFields {...args} />}
          />
        ) : null
      }
      getRowSx={(row) => {
        const selected = selectedIdSet.has(row.id);
        const drawerOpen = effectiveDetailCandidate?.id === row.id;
        const verify =
          row.entity_type === 'customer_dealer_token' &&
          row.context &&
          row.context.needs_name_review === true;
        if (verify) {
          return (theme) => ({
            ...(selected || drawerOpen ? { bgcolor: 'action.selected' } : {}),
            boxShadow: `inset 3px 0 0 ${theme.palette.warning.main}`,
          });
        }
        if (selected || drawerOpen) {
          return { bgcolor: 'action.selected' };
        }
        return undefined;
      }}
    />
  );

  return (
    <Stack spacing={2} data-testid="dsi-import-job-resolution">
      <Typography variant="subtitle2">Resolve blockers for this import</Typography>
      <Alert severity="info">
        <Typography variant="body2" component="div">
          <strong>Validate → Resolve → Revalidate → Apply</strong>. Use entity tabs for distributors, customers, and
          products; use <strong>Region &amp; channel</strong> when file geography does not match the catalog.{' '}
          <Link component={NextLink} href={`/admin/imports?job=${importJobId}`}>
            Import job workspace
          </Link>{' '}
          ·{' '}
          <Link component={NextLink} href={`/admin/mappings?import_job_id=${importJobId}`}>
            Mapping queue (legacy)
          </Link>
          .
        </Typography>
      </Alert>

      {showBlockerEmptyState ? (
        <Alert severity="warning" data-testid="dsi-blocker-empty-state">
          <Typography variant="body2" component="div">
            {dataQualityBlockers > 0 ? (
              <>
                <strong>{dataQualityBlockers}</strong> row(s) have a blank product identifier — there is no steward
                candidate for these. Fix the product column mapping on the mapping step, exclude the source file/sheet,
                or remove blank product lines from the file, then re-validate.
                {stewardMapBlockers > 0 || masterMergeExcluded > 0 ? ' ' : null}
              </>
            ) : null}
            {stewardMapBlockers > 0 ? (
              <>
                <strong>{stewardMapBlockers}</strong> row(s) still need steward mapping (unmapped customers or products).
                Open the matching entity tab and clear default filters, or use the global{' '}
                <Link component={NextLink} href={`/admin/mappings?import_job_id=${importJobId}`}>
                  mapping queue
                </Link>
                .
                {masterMergeExcluded > 0 ? ' ' : null}
              </>
            ) : null}
            {masterMergeExcluded > 0 ? (
              <>
                <strong>{masterMergeExcluded}</strong> sell-out row(s) are held for master-data alias conflicts — merge
                duplicate customers on{' '}
                <Link component={NextLink} href="/admin/customers/duplicates?tab=alias_scope">
                  Alias-scope conflicts
                </Link>
                , then re-validate this job.
              </>
            ) : null}
          </Typography>
        </Alert>
      ) : null}

      <StewardResolutionPlanToolbar
        plan={{
          candidatesCount: candidatesTotal,
          readyCount: plan.readyPlanCandidateIds.length,
          suggestionsQuery: plan.suggestionsQuery,
        }}
        testIds={DSI_ENGINE_CONFIG.planToolbarTestIds}
        onApplyAllReady={() => plan.setApplyAllConfirmOpen(true)}
        applyAllPending={plan.applyResolutionPlan.isPending}
        applyAllDisabled={
          plan.readyPlanCandidateIds.length === 0 ||
          planApplyBlocked ||
          (stewardOverlayBusy && !plan.applyResolutionPlan.isPending)
        }
        applyAllLabel={`Apply all ready (${plan.readyPlanCandidateIds.length})`}
        applyAllTestId="dsi-resolution-plan-apply-all"
        dsiExtras={{
          resolutionPlan: plan.resolutionPlan,
          planGlobalSuspicious: plan.planGlobalSuspicious,
          setPlanGlobalSuspicious: plan.setPlanGlobalSuspicious,
          planLoadToken: plan.planLoadToken,
          planTableRows: plan.planTableRows,
          refreshPlanEffective: plan.refreshPlanEffective,
          overridesPayload: plan.overridesPayload,
        }}
      />

      {supervisedAutoResolvedRows.length > 0 ? (
        <Alert severity="info" data-testid="dsi-supervised-auto-resolve-section">
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Auto-resolved from prior decisions — review before apply
          </Typography>
          <Typography variant="body2" component="div">
            {supervisedAutoResolvedRows.map((row) => {
              const cid = row.candidate_id;
              const label = row.suggested_target_label ?? row.suggested_target_id ?? '—';
              const nk = row.normalized_key ?? '';
              return (
                <Box key={String(cid)} sx={{ mb: 0.5 }}>
                  <strong>{String(nk)}</strong> → {String(label)} (ready — supervised auto-resolution)
                </Box>
              );
            })}
          </Typography>
        </Alert>
      ) : null}

      {planInitialLoading ? (
        <DsiStewardLoadingCallout
          message="Computing resolution plan…"
          detail="Plan is scoped to the current page of candidates. Large pages may take a few seconds."
          testId="dsi-resolution-plan-loading"
        />
      ) : null}

      {candidatesError ? (
        <Alert severity="error" data-testid="dsi-candidates-load-error">
          {safeDisplayError(candidatesError)}
        </Alert>
      ) : null}

      <StewardWorkspaceViewportShell
        rootTestId="dsi-steward-workspace-viewport-shell"
        left={
          <>
            {planApplySummary ? (
              <Alert
                severity={planApplySummary.severity}
                data-testid="dsi-plan-apply-summary"
                onClose={() => setPlanApplySummary(null)}
              >
                {planApplySummary.message}
              </Alert>
            ) : null}
            {plan.applyResolutionPlan.isError && !planApplySummary ? (
              <Alert severity="error" data-testid="dsi-plan-apply-error">
                Apply failed. Check the activity bell or try again with a smaller batch.
              </Alert>
            ) : null}
            <Box sx={{ flex: 1, minHeight: 0, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
              {candidateWorkspace}
            </Box>

            {tabbedMode && isCandidateTab ? (
              <StewardCandidatesPagination
                page={candidatesPage.page}
                pageCount={clientQueueFilterActive ? filteredPageCount : candidatesPage.pageCount}
                pageSize={candidatesPage.pageSize}
                total={clientQueueFilterActive ? filteredCandidates.length : candidatesPage.total}
                skip={candidatesPage.skip}
                pageItemCount={displayedCandidates.length}
                busy={candidatesPage.query.isFetching}
                onPageChange={candidatesPage.setPage}
                onPageSizeChange={candidatesPage.setPageSize}
              />
            ) : null}
          </>
        }
        drawer={
          effectiveDetailCandidate && isCandidateTab ? (
            <StewardCandidateDrawer
              title={DSI_ENGINE_CONFIG.titleForCandidate(effectiveDetailCandidate)}
              onClose={() => setDetailCandidate(null)}
              rootTestId={DSI_ENGINE_CONFIG.drawerTestIds.root}
              closeTestId={DSI_ENGINE_CONFIG.drawerTestIds.close}
              ariaLabel={DSI_ENGINE_CONFIG.drawerTestIds.ariaLabel}
            >
              <DsiMappingStewardPanel
                importJobId={importJobId}
                candidate={effectiveDetailCandidate}
                planRow={plan.planByCandidateId.get(effectiveDetailCandidate.id) ?? null}
                onRowActionStart={(candidateId) => setRowActionPendingId(candidateId)}
                onRowActionEnd={() => setRowActionPendingId(null)}
                onDone={() => setDetailCandidate(null)}
                onStewardFastComplete={plan.evictResolvedCandidates}
                lookupPeerCandidate={lookupPeerCandidateByNormalizedKey}
                onOpenPeerByNormalizedKey={openPeerCandidateByNormalizedKey}
                customerNormalizedKeysOnPage={customerNormalizedKeysOnPage}
                duplicateClusterMembers={duplicateClusterMembersForSelection}
              />
            </StewardCandidateDrawer>
          ) : null
        }
      />

      <StewardBulkSection
        bulk={bulk}
        plan={plan}
        testIds={DSI_ENGINE_CONFIG.bulkTestIds}
        formatProposedLabel={DSI_ENGINE_CONFIG.formatBulkProposedLabel}
        formatAliasEvidence={DSI_ENGINE_CONFIG.formatBulkAliasEvidence}
      />

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <StewardPendingButton
          variant="outlined"
          pending={revalidatePipelineBusy}
          pendingLabel="Re-running import validation…"
          disabled={stewardOverlayBusy && !revalidatePipelineBusy}
          onClick={() => void plan.dsiRevalidateFromServer.mutateAsync().catch(() => {})}
          data-testid="dsi-import-revalidate-server"
        >
          Re-run import validation (server)
        </StewardPendingButton>
        <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 520 }}>
          Runs the DSI import validator on the server so staging and blockers refresh. Use after steward saves (single-row,
          bulk, or resolution plan apply). This is <strong>not</strong> the same as <strong>Refresh suggestions</strong>{' '}
          (read-only plan recompute).
        </Typography>
      </Stack>
      {plan.dsiRevalidateFromServer.isError ? (
        <Alert severity="error">{safeDisplayError(plan.dsiRevalidateFromServer.error)}</Alert>
      ) : null}

      <Drawer
        anchor="right"
        open={plan.suggestionDrawerId != null}
        onClose={() => plan.setSuggestionDrawerId(null)}
        PaperProps={{ sx: { width: { xs: '100%', sm: 440 }, maxWidth: '100%' } }}
      >
        <Box sx={{ p: 2 }} data-testid="dsi-resolution-suggestion-drawer">
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Typography variant="subtitle1">Resolution detail</Typography>
            <Button size="small" onClick={() => plan.setSuggestionDrawerId(null)}>
              Close
            </Button>
          </Stack>
          <Divider sx={{ mb: 2 }} />
          {plan.planDrawerRow ? (
            <PlanDialogRowDetail
              r={plan.planDrawerRow}
              candidate={candidatesById[Number(plan.planDrawerRow.candidate_id)]}
              regions={plan.regions}
              channels={plan.channels}
              planOverrideMap={plan.planOverrideMap}
              patchPlanOverride={plan.patchPlanOverride}
            />
          ) : (
            <Typography variant="body2" color="text.secondary" data-testid="dsi-resolution-plan-detail-empty">
              No suggestion row for this candidate.
            </Typography>
          )}
        </Box>
      </Drawer>
    </Stack>
  );
}
