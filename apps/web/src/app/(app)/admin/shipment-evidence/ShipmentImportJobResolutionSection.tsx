'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import { BulkSelectionToolbar } from '@/components/bulkTable/BulkSelectionToolbar';

import { StewardCandidatesPagination } from '@/features/import-steward/StewardCandidatesPagination';
import { StewardPendingButton } from '@/features/import-steward/StewardPendingButton';
import { StewardCandidateFilters } from '@/features/import-steward/StewardCandidateFilters';
import { ImportStewardCandidateWorkspace } from '@/features/import-steward/ImportStewardCandidateWorkspace';
import { StewardWorkspaceViewportShell } from '@/features/import-steward/StewardWorkspaceViewportShell';
import { computeImportStewardSelectionHeaderState } from '@/features/import-steward/importStewardSelectionUtils';
import { paginateStewardCandidateRows } from '@/features/import-steward/stewardCandidateFilterLogic';
import { StewardCandidateDrawer } from '@/features/import-steward/StewardCandidateDrawer';
import { StewardEntityTabsBar } from '@/features/import-steward/StewardEntityTabsBar';
import { StewardResolutionPlanToolbar } from '@/features/import-steward/StewardResolutionPlanToolbar';
import { StewardBulkSection } from '@/features/import-steward/StewardBulkSection';
import { useStewardBulkSteward } from '@/features/import-steward/useStewardBulkSteward';
import { useStewardResolutionPlan } from '@/features/import-steward/useStewardResolutionPlan';
import type { StewardPlanApplyFeedback } from '@/features/import-steward/stewardEngine.types';
import type { InboundEvidenceMappingCandidateRow } from '@/features/import-steward/inboundEvidenceMappingCandidateWorkspaceColumns';
import { safeDisplayError } from '@/lib/api';
import { useQueryClient } from '@tanstack/react-query';

import {
  shipmentContextNeedsNameReview,
  shipmentEntityChipLabel,
  type ShipmentMappingCandidateRow,
} from './shipmentMappingCandidateDisplay';
import {
  ShipmentCandidateInlineActions,
  ShipmentStewardActionsProvider,
} from './shipmentStewardRowActions';
import { ShipmentBulkActionInlineForm } from './ShipmentBulkActionInlineForm';
import { ShipmentPlanOptionsMenu } from './ShipmentPlanOptionsMenu';
import {
  defaultShipmentStewardFiltersForTab,
  formatShipmentEntityTabLabel,
  SHIPMENT_ENTITY_TAB_DEFS,
  shipmentStewardFiltersMatchTabDefault,
  type ShipmentEntityTabId,
} from './shipmentEntityTabs';
import { filterShipmentStewardCandidates } from './shipmentStewardCandidateFilterLogic';
import { invalidateShipmentImportJobStewardQueries, SHIPMENT_STEWARD_CONFIG } from './shipmentSteward.config';
import { useShipmentCandidatesPage } from './useShipmentCandidatesPage';
import { useShipmentEntityTabCounts } from './useShipmentEntityTabCounts';
import { SHIPMENT_ENGINE_CONFIG } from './shipmentSteward.engineConfig';
import { ShipmentMappingStewardPanel } from './ShipmentMappingStewardPanel';
import { buildShipmentResolutionWorkspaceColumns } from './shipmentResolutionWorkspaceTableProps';
import { ShipmentEntityStewardPanelLegacy } from './ShipmentEntityStewardPanelLegacy';
import { useShipmentPlanEffectiveRefresh } from './useShipmentPlanEffectiveRefresh';

function formatShipmentPlanApplySummary(data: Record<string, unknown>): StewardPlanApplyFeedback {
  const applied = Number(data.applied ?? 0);
  const failed = Number(data.failed ?? 0);
  const skipped = Number(data.skipped_not_ready ?? 0);
  if (applied > 0 && failed === 0) {
    return { severity: 'success', message: `Applied ${applied} plan row(s).` };
  }
  if (applied > 0) {
    return {
      severity: 'warning',
      message: `Partial success: applied ${applied}, failed ${failed}, skipped ${skipped}.`,
    };
  }
  return {
    severity: 'warning',
    message: `No rows applied (failed ${failed}, skipped ${skipped}).`,
  };
}

function shipmentSummaryChips(summary: Record<string, unknown>) {
  return (
    <>
      <Chip size="small" label={`Candidates ${String(summary.total ?? '—')}`} />
      <Chip
        size="small"
        color="success"
        variant="outlined"
        label={`Ready ${String(summary.ready ?? '—')}`}
      />
      <Chip
        size="small"
        color="warning"
        variant="outlined"
        label={`Needs work ${String(summary.not_ready ?? '—')}`}
      />
      <Chip size="small" variant="outlined" label={`On hold ${String(summary.hold ?? '—')}`} />
    </>
  );
}

export function ShipmentImportJobResolutionSection({
  importJobId,
  shipmentPipelineRunning = false,
  onInvalidate: onInvalidateProp,
  onAsyncPipelineStarted,
}: {
  importJobId: number | null;
  shipmentPipelineRunning?: boolean;
  onInvalidate?: () => void;
  onAsyncPipelineStarted?: (args: { importJobId: number; taskId?: string | null }) => void;
}) {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<ShipmentEntityTabId>('distributor');
  const [visitedTabs, setVisitedTabs] = useState<Set<ShipmentEntityTabId>>(() => new Set(['distributor']));
  const [filtersByTab, setFiltersByTab] = useState(() => ({
    distributor: defaultShipmentStewardFiltersForTab('distributor'),
    customer: defaultShipmentStewardFiltersForTab('customer'),
  }));
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkMode, setBulkMode] = useState<BulkTableSelectionMode>('normal');
  const [bulkProvNamesById, setBulkProvNamesById] = useState<Record<number, string>>({});
  const [planApplySummary, setPlanApplySummary] = useState<StewardPlanApplyFeedback | null>(null);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [detailCandidate, setDetailCandidate] = useState<ShipmentMappingCandidateRow | null>(null);
  const [rowActionPendingId, setRowActionPendingId] = useState<number | null>(null);
  const workspaceToolbarRef = useRef<HTMLDivElement | null>(null);

  const tabbedMode = importJobId != null;
  const activeFilters = filtersByTab[activeTab];

  const onInvalidate = useCallback(() => {
    if (importJobId == null) return;
    invalidateShipmentImportJobStewardQueries(qc, importJobId);
    onInvalidateProp?.();
  }, [importJobId, onInvalidateProp, qc]);

  const { counts, tabCountsQuery } = useShipmentEntityTabCounts(importJobId ?? 0, tabbedMode);

  useEffect(() => {
    setVisitedTabs((prev) => new Set([...prev, activeTab]));
  }, [activeTab]);

  const candidatesPage = useShipmentCandidatesPage(importJobId ?? 0, activeFilters, {
    enabled: tabbedMode && visitedTabs.has(activeTab),
    tabKey: activeTab,
  });

  const candidates = candidatesPage.candidates;
  const candidatesLoading =
    candidatesPage.query.isLoading ||
    (candidatesPage.query.isFetching && candidatesPage.candidates.length === 0);

  const plan = useStewardResolutionPlan({
    importJobId: importJobId ?? 0,
    candidates: candidates as unknown as InboundEvidenceMappingCandidateRow[],
    onInvalidate,
    onAsyncPipelineStarted,
    setSelectedIds,
    setPlanApplySummary,
    config: SHIPMENT_ENGINE_CONFIG,
    formatPlanApplySummary: formatShipmentPlanApplySummary,
  });

  const { refreshPlanEffective } = useShipmentPlanEffectiveRefresh({
    importJobId: importJobId ?? 0,
    candidateIds: candidates.map((c) => c.id),
    effectivePlanPath: SHIPMENT_ENGINE_CONFIG.effectivePlanPath!,
    planOverrideMap: plan.planOverrideMap,
    replaceResolutionPlan: plan.replaceResolutionPlan,
  });

  const shipmentRevalidateFromServer = plan.revalidateFromServer;

  const focusWorkspaceToolbar = useCallback(() => {
    workspaceToolbarRef.current?.querySelector<HTMLElement>('button')?.focus();
  }, []);

  const getBulkBodyExtras = useCallback(
    (action: string) => {
      if (action !== 'create_provisional_customer') return {};
      const display_names: Record<string, string> = {};
      for (const id of selectedIds) {
        display_names[String(id)] = (bulkProvNamesById[id] ?? '').trim();
      }
      return { display_names };
    },
    [selectedIds, bulkProvNamesById]
  );

  const validateBulkForm = useCallback(() => {
    if (selectedIds.length === 0) return false;
    return selectedIds.every((id) => (bulkProvNamesById[id] ?? '').trim().length > 0);
  }, [selectedIds, bulkProvNamesById]);

  const bulk = useStewardBulkSteward({
    importJobId: importJobId ?? 0,
    selectedIds,
    setSelectedIds,
    setBulkMode,
    onInvalidate,
    onBulkClosed: focusWorkspaceToolbar,
    onPlanRefresh: () => plan.refreshSuggestions(),
    onEvictResolvedCandidates: plan.evictResolvedCandidates,
    onShrinkPlanScope: plan.shrinkPlanScope,
    getBulkBodyExtras,
    validateBulkForm,
    config: SHIPMENT_ENGINE_CONFIG,
  });

  const closeBulkForm = useCallback(() => {
    setBulkMode('normal');
    setSelectedIds([]);
    setBulkProvNamesById({});
    bulk.setPreviewOpen(false);
    bulk.setBulkCustomerId('');
    bulk.setBulkDistributorId('');
    focusWorkspaceToolbar();
  }, [bulk, focusWorkspaceToolbar]);

  const filteredCandidates = useMemo(
    () =>
      filterShipmentStewardCandidates(
        candidates as ShipmentMappingCandidateRow[],
        activeFilters,
        plan.planByCandidateId
      ),
    [candidates, activeFilters, plan.planByCandidateId]
  );

  const clientQueueFilterActive = candidatesPage.clientQueueFilterActive;
  const filteredPageCount = Math.max(
    1,
    Math.ceil(filteredCandidates.length / Math.max(1, candidatesPage.pageSize))
  );

  const gridCandidates = useMemo(() => {
    if (!clientQueueFilterActive) return filteredCandidates;
    return paginateStewardCandidateRows(filteredCandidates, candidatesPage.page, candidatesPage.pageSize);
  }, [filteredCandidates, clientQueueFilterActive, candidatesPage.page, candidatesPage.pageSize]);

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

  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const visibleRowIds = useMemo(() => displayedCandidates.map((r) => r.id), [displayedCandidates]);
  const selectionHeader = useMemo(
    () => computeImportStewardSelectionHeaderState(visibleRowIds, selectedIdSet),
    [visibleRowIds, selectedIdSet]
  );

  const workspaceSelection = useMemo(
    () => ({
      selectedIds: selectedIdSet,
      visibleRowIds,
      headerState: selectionHeader,
      onToggle: (rowId: number) => {
        setSelectedIds((prev) => (prev.includes(rowId) ? prev.filter((x) => x !== rowId) : [...prev, rowId]));
      },
      onToggleAllVisible: () => {
        const allSelected = visibleRowIds.every((id) => selectedIdSet.has(id));
        setSelectedIds(
          allSelected
            ? selectedIds.filter((id) => !visibleRowIds.includes(id))
            : [...new Set([...selectedIds, ...visibleRowIds])]
        );
      },
    }),
    [selectedIdSet, visibleRowIds, selectionHeader, selectedIds]
  );

  useEffect(() => {
    setDetailCandidate(null);
    setSelectedIds([]);
    setBulkProvNamesById({});
  }, [importJobId, activeTab, candidatesPage.page, candidatesPage.pageSize]);

  const effectiveDetailCandidate = useMemo(() => {
    if (detailCandidate == null) return null;
    return displayedCandidates.find((c) => c.id === detailCandidate.id) ?? detailCandidate;
  }, [detailCandidate, displayedCandidates]);

  const stewardOverlayBusy =
    plan.applyResolutionPlan.isPending ||
    plan.suggestionsQuery.isFetching ||
    bulk.bulkPreview.isPending ||
    bulk.bulkApply.isPending ||
    refreshPlanEffective.isPending ||
    shipmentPipelineRunning;

  const revalidatePipelineBusy =
    shipmentPipelineRunning || shipmentRevalidateFromServer.isPending;

  const columns = useMemo(
    () =>
      buildShipmentResolutionWorkspaceColumns({
        planByCandidateId: plan.planByCandidateId,
        renderActionsCell: (row) => (
          <ShipmentCandidateInlineActions
            row={row as unknown as ShipmentMappingCandidateRow}
            onReview={(r) => setDetailCandidate(r)}
            pending={rowActionPendingId === row.id}
          />
        ),
      }),
    [plan.planByCandidateId, rowActionPendingId]
  );

  const openBulkWorkflow = useCallback(
    (action: string) => {
      bulk.setBulkAction(action);
      bulk.setBulkCustomerId('');
      bulk.setBulkDistributorId('');
      setBulkProvNamesById({});
      setBulkMode('selecting');
      if (selectedIds.length === 0 && displayedCandidates.length > 0) {
        setSelectedIds(displayedCandidates.map((c) => c.id));
      }
    },
    [bulk, displayedCandidates, selectedIds.length]
  );

  const selectVisibleReadyInGrid = useCallback(() => {
    const ready = displayedCandidates
      .filter((c) => plan.planByCandidateId.get(c.id)?.ready === true)
      .map((c) => c.id);
    setSelectedIds(ready);
    setBulkMode('selecting');
  }, [displayedCandidates, plan.planByCandidateId]);

  const planSummary =
    plan.resolutionPlan?.summary && typeof plan.resolutionPlan.summary === 'object'
      ? (plan.resolutionPlan.summary as Record<string, unknown>)
      : null;

  const bulkPlanSlice = useMemo(
    () => ({
      applyAllConfirmOpen: plan.applyAllConfirmOpen,
      setApplyAllConfirmOpen: plan.setApplyAllConfirmOpen,
      applyResolutionPlan: plan.applyResolutionPlan,
      readyPlanCandidateIds: plan.readyPlanCandidateIds,
      applyAllProvisionalStats: {
        provisionalCustomerReady: 0,
        unassignedGeoReady: 0,
        fallbackGeoReady: 0,
      },
    }),
    [
      plan.applyAllConfirmOpen,
      plan.setApplyAllConfirmOpen,
      plan.applyResolutionPlan,
      plan.readyPlanCandidateIds,
    ]
  );

  if (importJobId == null) {
    return (
      <Alert severity="info" data-testid="shipment-import-job-resolution-section">
        Upload and validate a shipment import job to load mapping candidates.
      </Alert>
    );
  }

  return (
    <ShipmentStewardActionsProvider importJobId={importJobId} onInvalidate={onInvalidate}>
      <Stack spacing={2} data-testid="shipment-import-job-resolution-section">
        {planApplySummary ? (
          <Alert severity={planApplySummary.severity} onClose={() => setPlanApplySummary(null)}>
            {planApplySummary.message}
          </Alert>
        ) : null}

        <StewardResolutionPlanToolbar
          plan={{
            candidatesCount: candidates.length,
            readyCount: plan.readyPlanCandidateIds.length,
            suggestionsQuery: plan.suggestionsQuery,
          }}
          testIds={SHIPMENT_ENGINE_CONFIG.planToolbarTestIds}
          copy={SHIPMENT_ENGINE_CONFIG.planToolbarCopy}
          onApplyAllReady={() => plan.setApplyAllConfirmOpen(true)}
          applyAllPending={plan.applyResolutionPlan.isPending}
          applyAllDisabled={
            plan.readyPlanCandidateIds.length === 0 || plan.applyResolutionPlan.isPending
          }
          applyAllLabel={`Apply all ready (${plan.readyPlanCandidateIds.length})`}
          applyAllTestId="shipment-resolution-plan-apply-all"
          summaryChipsSlot={planSummary ? shipmentSummaryChips(planSummary) : undefined}
          planOptionsSlot={
            <ShipmentPlanOptionsMenu
              planLoadToken={plan.planLoadToken}
              refreshPlanEffective={refreshPlanEffective}
              optionsOpenTestId={SHIPMENT_ENGINE_CONFIG.planToolbarTestIds.optionsOpen}
              optionsMenuTestId={SHIPMENT_ENGINE_CONFIG.planToolbarTestIds.optionsMenu}
              refreshEffectiveTestId={SHIPMENT_ENGINE_CONFIG.planToolbarTestIds.refreshEffective}
            />
          }
        />
        {refreshPlanEffective.isError ? (
          <Alert severity="error" data-testid={SHIPMENT_ENGINE_CONFIG.planToolbarTestIds.effectiveError}>
            {safeDisplayError(refreshPlanEffective.error)}
          </Alert>
        ) : null}

        <StewardWorkspaceViewportShell
          bordered
          rootTestId="shipment-steward-workspace-viewport-shell"
          left={
            <Box sx={{ flex: 1, minHeight: 0, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
              <ImportStewardCandidateWorkspace
                embedded
                keepTableWhenFilterEmpty
                rootTestId="shipment-steward-candidate-workspace"
                listDomainId={SHIPMENT_STEWARD_CONFIG.listDomainId}
                importJobId={importJobId}
                copy={SHIPMENT_STEWARD_CONFIG.listShellCopy}
                openRows={candidates as unknown as InboundEvidenceMappingCandidateRow[]}
                filteredRows={displayedCandidates as unknown as InboundEvidenceMappingCandidateRow[]}
                isLoading={candidatesLoading}
                busy={stewardOverlayBusy}
                columns={columns}
                selection={workspaceSelection}
                onRowClick={(row) => setDetailCandidate(row as unknown as ShipmentMappingCandidateRow)}
                getRowSx={(row) => {
                  const r = row as unknown as ShipmentMappingCandidateRow;
                  const selected = selectedIdSet.has(r.id);
                  const drawerOpen = effectiveDetailCandidate?.id === r.id;
                  const verify =
                    r.entity_type === 'shipment_customer_token' && shipmentContextNeedsNameReview(r.context);
                  if (verify) {
                    return (theme) => ({
                      ...(selected || drawerOpen ? { bgcolor: 'action.selected' } : {}),
                      boxShadow: `inset 3px 0 0 ${theme.palette.warning.main}`,
                      cursor: 'pointer',
                    });
                  }
                  if (selected || drawerOpen) {
                    return { bgcolor: 'action.selected', cursor: 'pointer' };
                  }
                  return { cursor: 'pointer' };
                }}
                tabsSlot={
                  <StewardEntityTabsBar
                    tabs={SHIPMENT_ENTITY_TAB_DEFS}
                    activeTab={activeTab}
                    onChange={setActiveTab}
                    counts={counts}
                    busy={stewardOverlayBusy}
                    testIdPrefix="shipment"
                    ariaLabel="Shipment entity resolution"
                    formatTabAriaLabel={formatShipmentEntityTabLabel}
                  />
                }
                filtersSlot={
                  <StewardCandidateFilters
                    filters={activeFilters}
                    onChange={(next) => setFiltersByTab((prev) => ({ ...prev, [activeTab]: next }))}
                    visibleCount={
                      clientQueueFilterActive ? filteredCandidates.length : displayedCandidates.length
                    }
                    totalCount={tabbedMode ? candidatesPage.total : Math.max(candidatesPage.total, candidates.length)}
                    hideEntityFilter
                    hidePartyFilter={activeTab !== 'distributor'}
                    clearToDefault={() => defaultShipmentStewardFiltersForTab(activeTab)}
                    isAtDefault={(filters) => shipmentStewardFiltersMatchTabDefault(filters, activeTab)}
                  />
                }
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
                          refreshPlanEffective.isPending
                        }
                        previewDangerLabel="Preview bulk steward"
                        previewDangerDisabled={
                          selectedIds.length === 0 || bulk.bulkPreview.isPending || !bulk.bulkFormReady
                        }
                        onPreviewDangerAction={() => void bulk.bulkPreview.mutateAsync()}
                      />
                    ) : (
                      <>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={displayedCandidates.length === 0 && selectedIds.length === 0}
                          onClick={() => openBulkWorkflow('map_customer')}
                          data-testid="shipment-bulk-map-open"
                        >
                          Bulk map…
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={displayedCandidates.length === 0 && selectedIds.length === 0}
                          onClick={() => openBulkWorkflow('create_provisional_customer')}
                          data-testid="shipment-bulk-provisional-open"
                        >
                          Bulk provisional…
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={!displayedCandidates.some((c) => plan.planByCandidateId.get(c.id)?.ready === true)}
                          onClick={selectVisibleReadyInGrid}
                          data-testid="shipment-plan-select-visible-ready"
                        >
                          Select visible ready
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={selectedIds.length === 0 || plan.applyResolutionPlan.isPending}
                          onClick={() => plan.applyResolutionPlan.mutate(selectedIds)}
                          data-testid="shipment-resolution-plan-apply-selected"
                        >
                          Apply selected ({selectedIds.length})
                        </Button>
                        <Button size="small" variant="text" onClick={() => setLegacyOpen(true)}>
                          Advanced panel…
                        </Button>
                        <Typography variant="caption" color="text.secondary">
                          {selectedIds.length} selected · Ready {plan.readyPlanCandidateIds.length}
                        </Typography>
                        <Box sx={{ flexGrow: 1 }} />
                      </>
                    )}
                    <StewardCandidatesPagination
                      page={candidatesPage.page}
                      pageCount={clientQueueFilterActive ? filteredPageCount : candidatesPage.pageCount}
                      pageSize={candidatesPage.pageSize}
                      total={clientQueueFilterActive ? filteredCandidates.length : candidatesPage.total}
                      skip={candidatesPage.skip}
                      pageItemCount={displayedCandidates.length}
                      onPageChange={candidatesPage.setPage}
                      onPageSizeChange={candidatesPage.setPageSize}
                    />
                  </Stack>
                }
                bulkFormSlot={
                  bulkMode === 'selecting' && selectedIds.length > 0 ? (
                    <ShipmentBulkActionInlineForm
                      bulk={bulk}
                      selectedIds={selectedIds}
                      bulkProvNamesById={bulkProvNamesById}
                      setBulkProvName={(id, name) =>
                        setBulkProvNamesById((prev) => ({ ...prev, [id]: name }))
                      }
                      onCancel={closeBulkForm}
                      testIds={SHIPMENT_ENGINE_CONFIG.bulkTestIds}
                    />
                  ) : null
                }
              />
            </Box>
          }
          drawer={
            effectiveDetailCandidate ? (
              <StewardCandidateDrawer
                title={`${shipmentEntityChipLabel(effectiveDetailCandidate.entity_type)} steward`}
                onClose={() => setDetailCandidate(null)}
                rootTestId={SHIPMENT_ENGINE_CONFIG.drawerTestIds.root}
                closeTestId={SHIPMENT_ENGINE_CONFIG.drawerTestIds.close}
                ariaLabel={SHIPMENT_ENGINE_CONFIG.drawerTestIds.ariaLabel}
              >
                <ShipmentMappingStewardPanel
                  candidate={effectiveDetailCandidate as ShipmentMappingCandidateRow}
                  planRow={plan.planByCandidateId.get(effectiveDetailCandidate.id) ?? null}
                  applyPlanPending={plan.applyResolutionPlan.isPending}
                  onApplyPlanRow={(candidateId) => plan.applyResolutionPlan.mutate([candidateId])}
                  rowActionPending={rowActionPendingId === effectiveDetailCandidate.id}
                />
              </StewardCandidateDrawer>
            ) : null
          }
        />

        <StewardBulkSection
          bulk={bulk}
          plan={bulkPlanSlice}
          testIds={SHIPMENT_ENGINE_CONFIG.bulkTestIds}
          formatProposedLabel={SHIPMENT_ENGINE_CONFIG.formatBulkProposedLabel}
          formatAliasEvidence={SHIPMENT_ENGINE_CONFIG.formatBulkAliasEvidence}
          showApplyAllDialog={false}
        />

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          <StewardPendingButton
            variant="outlined"
            pending={revalidatePipelineBusy}
            pendingLabel="Re-running import validation…"
            disabled={stewardOverlayBusy && !revalidatePipelineBusy}
            onClick={() => void shipmentRevalidateFromServer.mutateAsync().catch(() => {})}
            data-testid="shipment-import-revalidate-server"
          >
            Re-run import validation (server)
          </StewardPendingButton>
          <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 520 }}>
            Runs the shipment validator on the server so evidence lines and steward candidates refresh. Use after steward
            saves or column re-mapping. Not the same as <strong>Refresh plan</strong>.
          </Typography>
        </Stack>
        {shipmentRevalidateFromServer.isError ? (
          <Alert severity="error">{safeDisplayError(shipmentRevalidateFromServer.error)}</Alert>
        ) : null}

        <Dialog open={plan.applyAllConfirmOpen} onClose={() => plan.setApplyAllConfirmOpen(false)}>
          <DialogTitle>Apply all ready plan rows?</DialogTitle>
          <DialogContent>
            <Typography variant="body2">
              This will apply {plan.readyPlanCandidateIds.length} ready resolution plan row(s) for this job.
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => plan.setApplyAllConfirmOpen(false)}>Cancel</Button>
            <Button
              variant="contained"
              data-testid="shipment-resolution-plan-apply-all-confirm"
              onClick={() => {
                plan.setApplyAllConfirmOpen(false);
                plan.applyResolutionPlan.mutate(plan.readyPlanCandidateIds);
              }}
            >
              Apply {plan.readyPlanCandidateIds.length}
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog open={legacyOpen} onClose={() => setLegacyOpen(false)} maxWidth="xl" fullWidth>
          <DialogTitle>Shipment steward (advanced)</DialogTitle>
          <DialogContent>
            <Box sx={{ pt: 1 }}>
              <ShipmentEntityStewardPanelLegacy importJobId={importJobId} />
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setLegacyOpen(false)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Stack>
    </ShipmentStewardActionsProvider>
  );
}
