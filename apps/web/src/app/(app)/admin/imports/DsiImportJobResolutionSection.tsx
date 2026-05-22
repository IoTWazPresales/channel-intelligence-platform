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
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { BulkSelectionToolbar, type BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';

import {
  DsiBulkActionInlineForm,
  DsiBulkStewardSection,
  DsiCandidateStewardDrawer,
  DsiCandidatesPagination,
  DsiEntityTabsBar,
  DsiPendingButton,
  DsiCountryRegionFallback,
  DsiRegionChannelTabPanel,
  DsiResolutionPlanToolbar,
  isDsiEntityCandidateTab,
  type DsiRegionEvidenceDto,
  DsiStewardCandidateFilters,
  DsiStewardLoadingCallout,
  DSI_STEWARD_CONFIG,
  ImportStewardCandidateWorkspace,
  useDsiCandidatesPage,
  useDsiEntityTabCounts,
  PlanDialogRowDetail,
  computeImportStewardSelectionHeaderState,
  defaultDsiStewardCandidateFilterState,
  defaultDsiStewardFiltersForTab,
  dsiTabDependencyNudge,
  filterDsiStewardCandidates,
  formatPlanActionLabel,
  invalidateDsiImportJobStewardQueries,
  useDsiBulkSteward,
  useDsiResolutionPlan,
  type DsiBulkAction,
  type DsiCandidateRow,
  type DsiEntityTabId,
  type DsiStewardCandidateFilterState,
} from '@/features/import-steward';
import { safeDisplayError } from '@/lib/api';

import { buildDsiResolutionWorkspaceColumns } from './dsiResolutionWorkspaceTableProps';

export function DsiImportJobResolutionSection({
  importJobId,
  candidates: candidatesOverride,
  candidatesLoading: candidatesLoadingOverride,
  candidatesError: candidatesErrorOverride,
  onInvalidate,
}: {
  importJobId: number;
  /** Test / story override — skips paginated fetch when provided. */
  candidates?: DsiCandidateRow[];
  candidatesLoading?: boolean;
  candidatesError?: unknown;
  onInvalidate: () => void;
}) {
  const qc = useQueryClient();
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
  const [planApplySummary, setPlanApplySummary] = useState<string | null>(null);
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

  const { counts: tabCounts, openByTab } = useDsiEntityTabCounts(importJobId, tabbedMode);

  const isCandidateTab = isDsiEntityCandidateTab(activeTab);

  const candidatesPage = useDsiCandidatesPage(importJobId, activeFilters, {
    enabled: tabbedMode && visitedTabs.has(activeTab) && isCandidateTab,
  });

  const candidates = candidatesOverride ?? candidatesPage.candidates;
  const candidatesLoading = candidatesLoadingOverride ?? candidatesPage.query.isLoading;
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
    setSelectedIds,
    setPlanApplySummary,
  });

  const bulk = useDsiBulkSteward({
    importJobId,
    selectedIds,
    setSelectedIds,
    setBulkMode,
    onInvalidate,
    onBulkClosed: focusWorkspaceToolbar,
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
  });

  const closeBulkForm = useCallback(() => {
    setBulkMode('normal');
    setSelectedIds([]);
    bulk.setPreviewOpen(false);
    focusWorkspaceToolbar();
  }, [bulk, focusWorkspaceToolbar]);

  const displayedCandidates = useMemo(
    () => filterDsiStewardCandidates(candidates, activeFilters, plan.planByCandidateId),
    [candidates, activeFilters, plan.planByCandidateId]
  );

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

  const stewardOverlayBusy =
    bulk.bulkPreview.isPending ||
    bulk.bulkApply.isPending ||
    plan.applyResolutionPlan.isPending ||
    plan.refreshPlanEffective.isPending ||
    plan.dsiRevalidateFromServer.isPending;

  const stewardBusyMessage = useMemo(() => {
    if (bulk.bulkApply.isPending) return 'Applying bulk steward actions…';
    if (bulk.bulkPreview.isPending) return 'Building bulk steward preview…';
    if (plan.applyResolutionPlan.isPending) return 'Applying resolution plan…';
    if (plan.refreshPlanEffective.isPending) return 'Updating resolution plan after your edits…';
    if (plan.dsiRevalidateFromServer.isPending) return 'Re-running import validation on the server…';
    return undefined;
  }, [
    bulk.bulkApply.isPending,
    bulk.bulkPreview.isPending,
    plan.applyResolutionPlan.isPending,
    plan.refreshPlanEffective.isPending,
    plan.dsiRevalidateFromServer.isPending,
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
      }),
    [
      plan.planByCandidateId,
      isDsiRowTerminal,
      openStewardDrawer,
      plan.handleOpenSuggestionRow,
      rowActionPendingId,
    ]
  );

  const stewardDone = useCallback(() => {
    invalidateDsiImportJobStewardQueries(qc, importJobId, { includeImportJobsList: true });
    onInvalidate();
  }, [qc, importJobId, onInvalidate]);

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
            <DsiEntityTabsBar
              activeTab={activeTab}
              onChange={onTabChange}
              counts={tabCounts}
              busy={stewardOverlayBusy}
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
          <DsiStewardCandidateFilters
            filters={activeFilters}
            onChange={setActiveFilters}
            visibleCount={displayedCandidates.length}
            totalCount={Math.max(candidatesTotal, candidates.length)}
            hideEntityFilter={tabbedMode}
            hidePartyFilter={tabbedMode && activeTab !== 'distributor'}
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
                  Plan fallbacks only — map file tokens in the panel below.
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
            {activeTab === 'customer' && bulkMode !== 'selecting' ? (
              <DsiCountryRegionFallback
                importJobId={importJobId}
                enabled={plan.planRegionFallbackEnabled}
                onEnabledChange={plan.setPlanRegionFallbackEnabled}
                onRegionIdChange={plan.setPlanRegionId}
                disabled={stewardOverlayBusy}
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
                <DsiPendingButton
                  variant="outlined"
                  size="small"
                  pending={plan.applyResolutionPlan.isPending}
                  pendingLabel="Applying…"
                  disabled={
                    selectedReadyPlanIds.length === 0 ||
                    plan.refreshPlanEffective.isPending ||
                    stewardOverlayBusy
                  }
                  onClick={() =>
                    void plan.applyResolutionPlan
                      .mutateAsync({
                        candidateIds: selectedReadyPlanIds,
                        overrides: plan.overridesPayload(),
                        globalSuspicious: plan.planGlobalSuspicious,
                      })
                      .catch(() => {})
                  }
                  data-testid="dsi-resolution-plan-apply-selected"
                >
                  Apply selected ready ({selectedReadyPlanIds.length})
                </DsiPendingButton>
                <DsiPendingButton
                  variant="contained"
                  size="small"
                  pending={plan.applyResolutionPlan.isPending}
                  pendingLabel="Applying…"
                  disabled={
                    plan.readyPlanCandidateIds.length === 0 ||
                    plan.refreshPlanEffective.isPending ||
                    stewardOverlayBusy
                  }
                  onClick={() => plan.setApplyAllConfirmOpen(true)}
                  data-testid="dsi-resolution-plan-apply-all"
                >
                  Apply all ready ({plan.readyPlanCandidateIds.length})
                </DsiPendingButton>
              </>
            ) : (
              <Box sx={{ flexGrow: 1 }} />
            )}
          </Stack>
      }
      bulkFormSlot={
        bulkMode === 'selecting' ? (
          <DsiBulkActionInlineForm
            bulk={bulk}
            regions={plan.regions}
            channels={plan.channels}
            onCancel={closeBulkForm}
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
        <Typography variant="body2" component="motion.div">
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

      <DsiResolutionPlanToolbar
        candidatesCount={candidatesTotal}
        resolutionPlan={plan.resolutionPlan}
        planGlobalSuspicious={plan.planGlobalSuspicious}
        setPlanGlobalSuspicious={plan.setPlanGlobalSuspicious}
        planLoadToken={plan.planLoadToken}
        planTableRows={plan.planTableRows}
        suggestionsQuery={plan.suggestionsQuery}
        refreshPlanEffective={plan.refreshPlanEffective}
        overridesPayload={plan.overridesPayload}
      />

      {planInitialLoading ? (
        <DsiStewardLoadingCallout
          message="Computing resolution plan…"
          detail="Plan is scoped to the current page of candidates. Large pages may take a few seconds."
          testId="dsi-resolution-plan-loading"
        />
      ) : null}

      {plan.suggestionsQuery.isError ? (
        <Alert severity="error" data-testid="dsi-resolution-plan-error">
          {safeDisplayError(plan.suggestionsQuery.error)}
        </Alert>
      ) : null}

      {candidatesError ? (
        <Alert severity="error" data-testid="dsi-candidates-load-error">
          {safeDisplayError(candidatesError)}
        </Alert>
      ) : null}

      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          alignItems: 'stretch',
          gap: 0,
          minHeight: 360,
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {planApplySummary ? (
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              flexWrap="wrap"
              useFlexGap
              data-testid="dsi-plan-apply-summary"
            >
              <Typography variant="caption" color="success.main" sx={{ fontWeight: 500 }}>
                {planApplySummary}
              </Typography>
              <Button size="small" variant="text" onClick={() => setPlanApplySummary(null)}>
                Dismiss
              </Button>
            </Stack>
          ) : null}
          {candidateWorkspace}

          {tabbedMode && isCandidateTab ? (
            <DsiCandidatesPagination
              page={candidatesPage.page}
              pageCount={candidatesPage.pageCount}
              pageSize={candidatesPage.pageSize}
              total={candidatesPage.total}
              skip={candidatesPage.skip}
              pageItemCount={candidates.length}
              busy={candidatesPage.query.isFetching || stewardOverlayBusy}
              onPageChange={candidatesPage.setPage}
              onPageSizeChange={candidatesPage.setPageSize}
            />
          ) : null}
        </Box>

        {effectiveDetailCandidate && isCandidateTab ? (
          <DsiCandidateStewardDrawer
            importJobId={importJobId}
            candidate={effectiveDetailCandidate}
            planRow={plan.planByCandidateId.get(effectiveDetailCandidate.id) ?? null}
            onClose={() => setDetailCandidate(null)}
            onRowActionStart={(candidateId) => setRowActionPendingId(candidateId)}
            onRowActionEnd={() => setRowActionPendingId(null)}
            onDone={stewardDone}
          />
        ) : null}
      </Box>

      <DsiBulkStewardSection
        bulkMode={bulkMode}
        setBulkMode={setBulkMode}
        selectedIds={selectedIds}
        setSelectedIds={setSelectedIds}
        displayedCandidateIds={displayedCandidates.map((c) => c.id)}
        bulk={bulk}
        plan={plan}
        regions={plan.regions}
        channels={plan.channels}
        stewardOverlayBusy={stewardOverlayBusy}
      />

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <DsiPendingButton
          variant="outlined"
          pending={plan.dsiRevalidateFromServer.isPending}
          pendingLabel="Re-running import validation…"
          disabled={stewardOverlayBusy && !plan.dsiRevalidateFromServer.isPending}
          onClick={() => void plan.dsiRevalidateFromServer.mutateAsync().catch(() => {})}
          data-testid="dsi-import-revalidate-server"
        >
          Re-run import validation (server)
        </DsiPendingButton>
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
