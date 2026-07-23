'use client';

import {
  Alert,
  Box,
  Button,
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
import { paginateDsiStewardCandidateRows } from '@/features/import-steward/dsiStewardCandidateFilterLogic';
import { ShipmentCandidateStewardDrawer } from '@/features/import-steward/ShipmentCandidateStewardDrawer';
import {
  shipmentContextNeedsNameReview,
  type ShipmentMappingCandidateRow,
} from '@/features/import-steward/shipmentMappingCandidateDisplay';
import {
  ShipmentCandidateInlineActions,
  ShipmentStewardActionsProvider,
} from '@/features/import-steward/shipmentStewardRowActions';
import { ShipmentBulkStewardSection } from '@/features/import-steward/ShipmentBulkStewardSection';
import { StewardEntityTabsBar } from '@/features/import-steward/StewardEntityTabsBar';
import { ShipmentResolutionPlanToolbar } from '@/features/import-steward/ShipmentResolutionPlanToolbar';
import {
  defaultShipmentStewardFiltersForTab,
  formatShipmentEntityTabLabel,
  SHIPMENT_ENTITY_TAB_DEFS,
  shipmentStewardFiltersMatchTabDefault,
  type ShipmentEntityTabId,
} from '@/features/import-steward/shipmentEntityTabs';
import { filterShipmentStewardCandidates } from '@/features/import-steward/shipmentStewardCandidateFilterLogic';
import type { InboundEvidenceMappingCandidateRow } from '@/features/import-steward/inboundEvidenceMappingCandidateWorkspaceColumns';
import { invalidateShipmentImportJobStewardQueries, SHIPMENT_STEWARD_CONFIG } from '@/features/import-steward/shipmentSteward.config';
import { useShipmentBulkSteward } from '@/features/import-steward/useShipmentBulkSteward';
import { useShipmentCandidatesPage } from '@/features/import-steward/useShipmentCandidatesPage';
import { useShipmentEntityTabCounts } from '@/features/import-steward/useShipmentEntityTabCounts';
import {
  useShipmentResolutionPlan,
  type ShipmentPlanApplyFeedback,
} from '@/features/import-steward/useShipmentResolutionPlan';
import { safeDisplayError } from '@/lib/api';
import { useQueryClient } from '@tanstack/react-query';

import { buildShipmentResolutionWorkspaceColumns } from './shipmentResolutionWorkspaceTableProps';
import { ShipmentEntityStewardPanelLegacy } from './ShipmentEntityStewardPanelLegacy';

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
  const [planApplySummary, setPlanApplySummary] = useState<ShipmentPlanApplyFeedback | null>(null);
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

  const plan = useShipmentResolutionPlan({
    importJobId: importJobId ?? 0,
    candidates: candidates as unknown as InboundEvidenceMappingCandidateRow[],
    onInvalidate,
    onAsyncPipelineStarted,
    setSelectedIds,
    setPlanApplySummary,
  });

  const bulk = useShipmentBulkSteward({
    importJobId: importJobId ?? 0,
    selectedIds,
    setSelectedIds,
    setBulkMode,
    onInvalidate,
    onBulkClosed: () => workspaceToolbarRef.current?.querySelector<HTMLElement>('button')?.focus(),
  });

  const filteredCandidates = useMemo(
    () =>
      filterShipmentStewardCandidates(
        candidates as unknown as ShipmentMappingCandidateRow[],
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
    return paginateDsiStewardCandidateRows(filteredCandidates, candidatesPage.page, candidatesPage.pageSize);
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
  }, [importJobId, activeTab, candidatesPage.page, candidatesPage.pageSize]);

  const effectiveDetailCandidate = useMemo(() => {
    if (detailCandidate == null) return null;
    return displayedCandidates.find((c) => c.id === detailCandidate.id) ?? detailCandidate;
  }, [detailCandidate, displayedCandidates]);

  const stewardOverlayBusy =
    plan.applyResolutionPlan.isPending ||
    plan.suggestionsQuery.isFetching ||
    bulk.bulkApply.isPending ||
    shipmentPipelineRunning;

  const revalidatePipelineBusy =
    shipmentPipelineRunning || plan.shipmentRevalidateFromServer.isPending;

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

  const openBulkWorkflow = useCallback((action: typeof bulk.bulkAction) => {
    bulk.setBulkAction(action);
    bulk.resetBulkForm();
    setBulkMode('selecting');
    if (selectedIds.length === 0 && displayedCandidates.length > 0) {
      setSelectedIds(displayedCandidates.map((c) => c.id));
    }
  }, [bulk, displayedCandidates, selectedIds.length]);

  const selectVisibleReadyInGrid = useCallback(() => {
    const ready = displayedCandidates
      .filter((c) => plan.planByCandidateId.get(c.id)?.ready === true)
      .map((c) => c.id);
    setSelectedIds(ready);
    setBulkMode('selecting');
  }, [displayedCandidates, plan.planByCandidateId]);

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

        <ShipmentResolutionPlanToolbar
          candidatesCount={candidates.length}
          planByCandidateId={plan.planByCandidateId}
          readyPlanCandidateIds={plan.readyPlanCandidateIds}
          suggestionsQuery={plan.suggestionsQuery}
          applyResolutionPlan={plan.applyResolutionPlan}
          applyAllConfirmOpen={plan.applyAllConfirmOpen}
          setApplyAllConfirmOpen={plan.setApplyAllConfirmOpen}
        />

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
                      onExitSelectionMode={() => {
                        setBulkMode('normal');
                        setSelectedIds([]);
                        bulk.resetBulkForm();
                      }}
                      onSelectAllVisible={() => setSelectedIds(displayedCandidates.map((c) => c.id))}
                      onDeselectAll={() => setSelectedIds([])}
                      busy={bulk.bulkApply.isPending || plan.applyResolutionPlan.isPending}
                      previewDangerLabel="Apply bulk steward"
                      previewDangerDisabled={selectedIds.length === 0 || bulk.bulkApply.isPending || !bulk.bulkFormReady}
                      onPreviewDangerAction={() => void bulk.bulkApply.mutateAsync()}
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
                <ShipmentBulkStewardSection
                  bulkMode={bulkMode}
                  selectedIds={selectedIds}
                  bulk={bulk}
                  stewardOverlayBusy={stewardOverlayBusy}
                />
              }
            />
            </Box>
          }
          drawer={
            effectiveDetailCandidate ? (
              <ShipmentCandidateStewardDrawer
                candidate={effectiveDetailCandidate}
                planRow={plan.planByCandidateId.get(effectiveDetailCandidate.id) ?? null}
                onClose={() => setDetailCandidate(null)}
                applyPlanPending={plan.applyResolutionPlan.isPending}
                onApplyPlanRow={(candidateId) => plan.applyResolutionPlan.mutate([candidateId])}
                rowActionPending={rowActionPendingId === effectiveDetailCandidate.id}
              />
            ) : null
          }
        />

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          <StewardPendingButton
            variant="outlined"
            pending={revalidatePipelineBusy}
            pendingLabel="Re-running import validation…"
            disabled={stewardOverlayBusy && !revalidatePipelineBusy}
            onClick={() => void plan.shipmentRevalidateFromServer.mutateAsync().catch(() => {})}
            data-testid="shipment-import-revalidate-server"
          >
            Re-run import validation (server)
          </StewardPendingButton>
          <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 520 }}>
            Runs the shipment validator on the server so evidence lines and steward candidates refresh. Use after steward
            saves or column re-mapping. Not the same as <strong>Refresh plan</strong>.
          </Typography>
        </Stack>
        {plan.shipmentRevalidateFromServer.isError ? (
          <Alert severity="error">{safeDisplayError(plan.shipmentRevalidateFromServer.error)}</Alert>
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
