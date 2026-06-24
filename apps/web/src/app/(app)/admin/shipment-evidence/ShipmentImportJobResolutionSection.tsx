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
  Paper,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { DsiCandidatesPagination } from '@/features/import-steward/DsiCandidatesPagination';
import { DsiStewardCandidateFilters } from '@/features/import-steward/DsiStewardCandidateFilters';
import { defaultDsiStewardFiltersForTab } from '@/features/import-steward/dsiEntityTabs';
import { filterDsiStewardCandidates } from '@/features/import-steward/dsiStewardCandidateFilterLogic';
import {
  buildInboundEvidenceMappingCandidateWorkspaceColumns,
  type InboundEvidenceMappingCandidateRow,
} from '@/features/import-steward/inboundEvidenceMappingCandidateWorkspaceColumns';
import { ImportStewardCandidateWorkspace } from '@/features/import-steward/ImportStewardCandidateWorkspace';
import { computeImportStewardSelectionHeaderState } from '@/features/import-steward/importStewardSelectionUtils';
import { ShipmentCandidateStewardDrawer } from '@/features/import-steward/ShipmentCandidateStewardDrawer';
import {
  shipmentContextNeedsNameReview,
  type ShipmentMappingCandidateRow,
} from '@/features/import-steward/shipmentMappingCandidateDisplay';
import {
  ShipmentCandidateInlineActions,
  ShipmentStewardActionsProvider,
} from '@/features/import-steward/shipmentStewardRowActions';
import { invalidateShipmentImportJobStewardQueries, SHIPMENT_STEWARD_CONFIG } from '@/features/import-steward/shipmentSteward.config';
import {
  SHIPMENT_ENTITY_TABS,
  type ShipmentEntityTabId,
  useShipmentEntityTabCounts,
} from '@/features/import-steward/useShipmentEntityTabCounts';
import { useShipmentCandidatesPage } from '@/features/import-steward/useShipmentCandidatesPage';
import {
  useShipmentResolutionPlan,
  type ShipmentPlanApplyFeedback,
} from '@/features/import-steward/useShipmentResolutionPlan';
import { useQueryClient } from '@tanstack/react-query';

import { ShipmentEntityStewardPanelLegacy } from './ShipmentEntityStewardPanelLegacy';

export function ShipmentImportJobResolutionSection({ importJobId }: { importJobId: number | null }) {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<ShipmentEntityTabId>('distributor');
  const [filtersByTab, setFiltersByTab] = useState(() => ({
    distributor: defaultDsiStewardFiltersForTab('distributor'),
    customer: defaultDsiStewardFiltersForTab('customer'),
  }));
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [planApplySummary, setPlanApplySummary] = useState<ShipmentPlanApplyFeedback | null>(null);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [detailCandidate, setDetailCandidate] = useState<ShipmentMappingCandidateRow | null>(null);

  const tabbedMode = importJobId != null;
  const activeFilters = filtersByTab[activeTab];
  const { counts, tabCountsQuery } = useShipmentEntityTabCounts(importJobId ?? 0, tabbedMode);

  const candidatesPage = useShipmentCandidatesPage(importJobId ?? 0, activeFilters, {
    enabled: tabbedMode,
    tabKey: activeTab,
  });

  const candidates = candidatesPage.candidates;
  const filteredRows = useMemo(
    () =>
      filterDsiStewardCandidates(
        candidates as unknown as InboundEvidenceMappingCandidateRow[],
        activeFilters
      ),
    [candidates, activeFilters]
  );

  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const visibleRowIds = useMemo(() => filteredRows.map((r) => r.id), [filteredRows]);
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

  const onInvalidate = useCallback(() => {
    if (importJobId == null) return;
    invalidateShipmentImportJobStewardQueries(qc, importJobId);
  }, [importJobId, qc]);

  const plan = useShipmentResolutionPlan({
    importJobId: importJobId ?? 0,
    candidates: filteredRows as unknown as InboundEvidenceMappingCandidateRow[],
    onInvalidate,
    setSelectedIds,
    setPlanApplySummary,
  });

  useEffect(() => {
    setDetailCandidate(null);
    setSelectedIds([]);
  }, [importJobId, activeTab, candidatesPage.page, candidatesPage.pageSize]);

  const effectiveDetailCandidate = useMemo(() => {
    if (detailCandidate == null) return null;
    return (
      (filteredRows as unknown as ShipmentMappingCandidateRow[]).find((c) => c.id === detailCandidate.id) ??
      detailCandidate
    );
  }, [detailCandidate, filteredRows]);

  const planInitialLoading = plan.suggestionsQuery.isFetching && !plan.suggestionsQuery.data;

  const columns = useMemo(
    () =>
      buildInboundEvidenceMappingCandidateWorkspaceColumns({
        renderActionsCell: (row) => (
          <ShipmentCandidateInlineActions row={row as unknown as ShipmentMappingCandidateRow} />
        ),
      }),
    []
  );

  const planReadyCount = plan.readyPlanCandidateIds.length;

  if (importJobId == null) {
    return (
      <Paper sx={{ p: 2 }} data-testid="shipment-import-job-resolution-section">
        <Alert severity="info">
          Set <strong>Import job ID</strong> in the filters above to load candidates for that job.
        </Alert>
      </Paper>
    );
  }

  const workspace = (
    <ImportStewardCandidateWorkspace
      listDomainId={SHIPMENT_STEWARD_CONFIG.listDomainId}
      importJobId={importJobId}
      copy={SHIPMENT_STEWARD_CONFIG.listShellCopy}
      openRows={candidates as unknown as InboundEvidenceMappingCandidateRow[]}
      filteredRows={filteredRows as unknown as InboundEvidenceMappingCandidateRow[]}
      isLoading={candidatesPage.query.isLoading}
      busy={plan.applyResolutionPlan.isPending || plan.suggestionsQuery.isFetching}
      columns={columns}
      selection={workspaceSelection}
      onRowClick={(row) => setDetailCandidate(row as unknown as ShipmentMappingCandidateRow)}
      getRowSx={(row) => {
        const r = row as unknown as ShipmentMappingCandidateRow;
        const selected = selectedIdSet.has(r.id);
        const drawerOpen = effectiveDetailCandidate?.id === r.id;
        const verify = r.entity_type === 'shipment_customer_token' && shipmentContextNeedsNameReview(r.context);
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
      filtersSlot={
        <DsiStewardCandidateFilters
          filters={activeFilters}
          onChange={(next) => setFiltersByTab((prev) => ({ ...prev, [activeTab]: next }))}
          visibleCount={filteredRows.length}
          totalCount={candidates.length}
          hideEntityFilter
          hidePartyFilter={activeTab !== 'distributor'}
          clearToDefault={() => defaultDsiStewardFiltersForTab(activeTab as 'distributor' | 'customer')}
        />
      }
      toolbarSlot={
        <DsiCandidatesPagination
          page={candidatesPage.page}
          pageCount={candidatesPage.pageCount}
          pageSize={candidatesPage.pageSize}
          total={candidatesPage.total}
          skip={candidatesPage.skip}
          pageItemCount={filteredRows.length}
          onPageChange={candidatesPage.setPage}
          onPageSizeChange={candidatesPage.setPageSize}
        />
      }
      keepTableWhenFilterEmpty
      rootTestId="shipment-steward-candidate-workspace"
      embedded
    />
  );

  return (
    <ShipmentStewardActionsProvider importJobId={importJobId} onInvalidate={onInvalidate}>
      <Paper sx={{ p: 2 }} data-testid="shipment-import-job-resolution-section">
        <Stack spacing={2}>
          <Typography variant="h6">{SHIPMENT_STEWARD_CONFIG.listShellCopy.title}</Typography>
          <Typography variant="body2" color="text.secondary">
            {SHIPMENT_STEWARD_CONFIG.listShellCopy.description}
          </Typography>

          {planApplySummary ? (
            <Alert severity={planApplySummary.severity} onClose={() => setPlanApplySummary(null)}>
              {planApplySummary.message}
            </Alert>
          ) : null}

          {planInitialLoading ? (
            <Alert severity="info" data-testid="shipment-resolution-plan-loading">
              Computing resolution plan for the current page of candidates…
            </Alert>
          ) : null}

          <Stack direction="row" spacing={1} flexWrap="wrap" data-testid="shipment-resolution-plan-toolbar">
            <Button
              size="small"
              variant="outlined"
              onClick={() => plan.refreshSuggestions()}
              disabled={plan.suggestionsQuery.isFetching}
              data-testid="shipment-resolution-plan-refresh"
            >
              {plan.suggestionsQuery.isFetching ? 'Computing plan…' : 'Refresh plan'}
            </Button>
            <Button
              size="small"
              variant="contained"
              disabled={planReadyCount === 0 || plan.applyResolutionPlan.isPending || planInitialLoading}
              onClick={() => plan.setApplyAllConfirmOpen(true)}
              data-testid="shipment-resolution-plan-apply-all"
            >
              Apply all ready ({planReadyCount})
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
              Bulk &amp; full panel…
            </Button>
          </Stack>

          <Tabs
            value={activeTab}
            onChange={(_, v: ShipmentEntityTabId) => setActiveTab(v)}
            data-testid="shipment-entity-tabs"
          >
            {SHIPMENT_ENTITY_TABS.map((tab) => (
              <Tab
                key={tab.id}
                value={tab.id}
                label={
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <span>{tab.label}</span>
                    {tabCountsQuery.isSuccess ? (
                      <Chip size="small" label={counts[tab.id].needsWork ?? 0} />
                    ) : null}
                  </Stack>
                }
              />
            ))}
          </Tabs>

          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
              alignItems: 'stretch',
              gap: 0,
              minHeight: 360,
            }}
          >
            <Box sx={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>{workspace}</Box>
            {effectiveDetailCandidate ? (
              <ShipmentCandidateStewardDrawer
                candidate={effectiveDetailCandidate}
                planRow={plan.planByCandidateId.get(effectiveDetailCandidate.id) ?? null}
                onClose={() => setDetailCandidate(null)}
              />
            ) : null}
          </Box>
        </Stack>

        <Dialog open={plan.applyAllConfirmOpen} onClose={() => plan.setApplyAllConfirmOpen(false)}>
          <DialogTitle>Apply all ready plan rows?</DialogTitle>
          <DialogContent>
            <Typography variant="body2">
              This will apply {planReadyCount} ready resolution plan row(s) for this job using the shipment-evidence API.
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
              Apply {planReadyCount}
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog open={legacyOpen} onClose={() => setLegacyOpen(false)} maxWidth="xl" fullWidth>
          <DialogTitle>Shipment steward (bulk &amp; legacy panel)</DialogTitle>
          <DialogContent>
            <Box sx={{ pt: 1 }}>
              <ShipmentEntityStewardPanelLegacy importJobId={importJobId} />
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setLegacyOpen(false)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Paper>
    </ShipmentStewardActionsProvider>
  );
}
