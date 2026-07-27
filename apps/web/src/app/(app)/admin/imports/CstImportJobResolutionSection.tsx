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
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import { BulkSelectionToolbar } from '@/components/bulkTable/BulkSelectionToolbar';
import {
  confidenceBand,
  confidenceBandColor,
  confidenceBandLabel,
} from '@/features/import-steward/confidenceBand';
import { StewardResolutionPlanToolbar } from '@/features/import-steward/StewardResolutionPlanToolbar';
import { StewardPendingButton } from '@/features/import-steward/StewardPendingButton';
import type { StewardPlanApplyFeedback } from '@/features/import-steward/stewardEngine.types';
import { useStewardResolutionPlan } from '@/features/import-steward/useStewardResolutionPlan';
import { ImportStewardCandidateWorkspace } from '@/features/import-steward/ImportStewardCandidateWorkspace';
import { StewardCandidateFilters } from '@/features/import-steward/StewardCandidateFilters';
import { StewardCandidatesPagination } from '@/features/import-steward/StewardCandidatesPagination';
import { StewardEntityTabsBar, type StewardEntityTabCounts } from '@/features/import-steward/StewardEntityTabsBar';
import { StewardWorkspaceViewportShell } from '@/features/import-steward/StewardWorkspaceViewportShell';
import {
  defaultStewardCandidateFilterState,
  type StewardCandidateFilterState,
} from '@/features/import-steward/stewardCandidateFilterLogic';
import { computeImportStewardSelectionHeaderState } from '@/features/import-steward/importStewardSelectionUtils';
import type { ImportStewardCandidateRowBase } from '@/features/import-steward/importStewardCandidateWorkspace.types';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

import { CstCandidateStewardDrawer } from './CstCandidateStewardDrawer';
import {
  CST_ENTITY_TAB_DEFS,
  CST_IMPORT_STEWARD_CONFIG,
  formatCstEntityTabLabel,
  invalidateCstImportStewardQueries,
  type CstEntityTabId,
  type CstMappingCandidate,
  type CstMappingState,
} from './cstImportSteward.config';
import { CST_IMPORT_ENGINE_CONFIG } from './cstImportSteward.engineConfig';
import { useCstCandidatesPage } from './useCstCandidatesPage';

export type CstStewardRow = ImportStewardCandidateRowBase & {
  token: string;
  suggestions?: CstMappingCandidate['suggestions'];
};

type CstEntityTabCounts = StewardEntityTabCounts<CstEntityTabId>;

function emptyCounts(): CstEntityTabCounts {
  return {
    product: { total: null, needsWork: null },
    location: { total: null, needsWork: null },
  };
}

function defaultCstFiltersForTab(tab: CstEntityTabId): StewardCandidateFilterState {
  return {
    ...defaultStewardCandidateFilterState(),
    entity: tab,
    party: 'all',
    queue: 'needs_review',
  };
}

function statusFilterFromQueue(queue: string): string {
  if (queue === 'all') return 'all';
  if (queue === 'ready_to_map') return 'open';
  if (queue === 'no_match') return 'needs_review';
  return 'needs_review';
}

function formatCstPlanApplySummary(data: Record<string, unknown>): StewardPlanApplyFeedback {
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

function cstPlanSummaryChips(summary: Record<string, unknown>) {
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
    </>
  );
}

function filterCstStewardRows(rows: CstStewardRow[], search: string): CstStewardRow[] {
  if (!search) return rows;
  const needle = search.toLowerCase();
  return rows.filter(
    (r) =>
      r.token.toLowerCase().includes(needle) ||
      r.status.toLowerCase().includes(needle) ||
      String(r.match_reason ?? '').toLowerCase().includes(needle) ||
      (r.suggestions ?? []).some((s) => s.label.toLowerCase().includes(needle)) ||
      String(r.row_count).includes(needle) ||
      (r.sample_raw_values ?? []).some((v) => String(v).toLowerCase().includes(needle))
  );
}

function ConfidenceBandCell({ score }: { score: number | null | undefined }) {
  const band = confidenceBand(score);
  if (band == null) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="cst-import-confidence-empty">
        —
      </Typography>
    );
  }
  return (
    <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="flex-end">
      <Chip
        size="small"
        variant="outlined"
        color={confidenceBandColor(band)}
        label={confidenceBandLabel(band)}
        data-testid="cst-import-confidence-band"
      />
      <Typography variant="caption" color="text.secondary">
        {Number(score).toFixed(2)}
      </Typography>
    </Stack>
  );
}

export function CstImportJobResolutionSection({
  importJobId,
  onInvalidate: onInvalidateProp,
}: {
  importJobId: number;
  onInvalidate?: () => void;
}) {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<CstEntityTabId>('product');
  const [activeFilters, setActiveFilters] = useState<StewardCandidateFilterState>(() =>
    defaultCstFiltersForTab('product')
  );
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkMode, setBulkMode] = useState<BulkTableSelectionMode>('normal');
  const [bulkEntityId, setBulkEntityId] = useState('');
  const [detailCandidate, setDetailCandidate] = useState<CstStewardRow | null>(null);
  const [actionFeedback, setActionFeedback] = useState<{
    message: string;
    severity: 'error' | 'warning';
  } | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [planApplySummary, setPlanApplySummary] = useState<StewardPlanApplyFeedback | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const statusParam = statusFilterFromQueue(activeFilters.queue);

  const onInvalidate = useCallback(() => {
    invalidateCstImportStewardQueries(qc, importJobId);
    onInvalidateProp?.();
  }, [importJobId, onInvalidateProp, qc]);

  const candidatesPage = useCstCandidatesPage(importJobId, activeTab, statusParam);

  const mappingStateQuery = useQuery({
    queryKey: CST_IMPORT_STEWARD_CONFIG.mappingStateQueryKey(importJobId),
    queryFn: ({ signal }) =>
      apiGet<CstMappingState>(`/api/v1/imports/jobs/${importJobId}/cst-mapping-state`, { signal }),
    enabled: importJobId > 0,
  });

  const customerId = mappingStateQuery.data?.customer_id ?? null;

  const countsQuery = useQuery({
    queryKey: ['imports', 'cst-candidate-counts', importJobId],
    enabled: importJobId > 0,
    queryFn: async ({ signal }) => {
      const [productAll, productOpen, locationAll, locationOpen] = await Promise.all([
        apiGet<{ total: number }>(
          `/api/v1/imports/jobs/${importJobId}/cst-candidates?skip=0&limit=1&entity=product&status=all`,
          { signal }
        ),
        apiGet<{ total: number }>(
          `/api/v1/imports/jobs/${importJobId}/cst-candidates?skip=0&limit=1&entity=product&status=open`,
          { signal }
        ),
        apiGet<{ total: number }>(
          `/api/v1/imports/jobs/${importJobId}/cst-candidates?skip=0&limit=1&entity=location&status=all`,
          { signal }
        ),
        apiGet<{ total: number }>(
          `/api/v1/imports/jobs/${importJobId}/cst-candidates?skip=0&limit=1&entity=location&status=open`,
          { signal }
        ),
      ]);
      const counts: CstEntityTabCounts = {
        product: { total: productAll.total, needsWork: productOpen.total },
        location: { total: locationAll.total, needsWork: locationOpen.total },
      };
      return counts;
    },
  });

  const counts = countsQuery.data ?? emptyCounts();

  const stewardRows: CstStewardRow[] = useMemo(
    () =>
      candidatesPage.candidates.map((c) => ({
        id: c.id,
        entity_type: c.entity_type,
        normalized_key: c.normalized_key,
        token: c.normalized_key,
        row_count: c.row_count,
        total_units: c.total_units ?? null,
        total_reported_value: c.total_reported_value ?? null,
        sample_raw_values: c.sample_raw_values ?? [],
        status: c.status,
        match_reason: c.match_reason ?? null,
        confidence_score: c.confidence_score ?? null,
        context: c.context ?? null,
        suggestions: c.suggestions ?? [],
        suggested_entity_id: c.suggested_entity_id,
      })),
    [candidatesPage.candidates]
  );

  const filteredRows = useMemo(
    () => filterCstStewardRows(stewardRows, debouncedSearch),
    [stewardRows, debouncedSearch]
  );

  const plan = useStewardResolutionPlan({
    importJobId,
    candidates: filteredRows,
    onInvalidate,
    setSelectedIds,
    setPlanApplySummary,
    config: CST_IMPORT_ENGINE_CONFIG,
    formatPlanApplySummary: formatCstPlanApplySummary,
  });

  const planSummary = plan.suggestionsQuery.data?.summary as Record<string, unknown> | undefined;

  useEffect(() => {
    setDetailCandidate(null);
    setSelectedIds([]);
    setBulkMode('normal');
    setBulkEntityId('');
    setSearchInput('');
    setDebouncedSearch('');
    setActiveFilters(defaultCstFiltersForTab(activeTab));
  }, [importJobId, activeTab]);

  useEffect(() => {
    setDetailCandidate(null);
    setSelectedIds([]);
  }, [candidatesPage.page, candidatesPage.pageSize, statusParam]);

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
        setSelectedIds((prev) =>
          prev.includes(rowId) ? prev.filter((x) => x !== rowId) : [...prev, rowId]
        );
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

  const effectiveDetailCandidate = useMemo(() => {
    if (detailCandidate == null) return null;
    return filteredRows.find((c) => c.id === detailCandidate.id) ?? detailCandidate;
  }, [detailCandidate, filteredRows]);

  const resolveMutation = useMutation({
    mutationFn: async (args: { candidateId: number; entityId: number }) =>
      apiPost(`/api/v1/imports/jobs/${importJobId}/cst-candidates/${args.candidateId}/resolve`, {
        entity_id: args.entityId,
      }),
    onSuccess: () => {
      setActionMsg('Mapped candidate. Re-run process if staging counts look stale.');
      setActionFeedback(null);
      onInvalidate();
    },
    onError: (e) => setActionFeedback({ message: safeDisplayError(e), severity: 'error' }),
  });

  const ignoreMutation = useMutation({
    mutationFn: async (candidateId: number) =>
      apiPost(`/api/v1/imports/jobs/${importJobId}/cst-candidates/${candidateId}/ignore`, {}),
    onSuccess: () => {
      setActionMsg('Ignored candidate.');
      setActionFeedback(null);
      onInvalidate();
    },
    onError: (e) => setActionFeedback({ message: safeDisplayError(e), severity: 'error' }),
  });

  const bulkResolveMutation = useMutation({
    mutationFn: async (args: { candidateIds: number[]; entityId: number }) =>
      apiPost(`/api/v1/imports/jobs/${importJobId}/cst-candidates/bulk-resolve`, {
        candidate_ids: args.candidateIds,
        entity_id: args.entityId,
      }),
    onSuccess: () => {
      setActionMsg('Bulk mapped selected candidates (same target).');
      setActionFeedback(null);
      setSelectedIds([]);
      setBulkMode('normal');
      setBulkEntityId('');
      onInvalidate();
    },
    onError: (e) => setActionFeedback({ message: safeDisplayError(e), severity: 'error' }),
  });

  const busy =
    resolveMutation.isPending || ignoreMutation.isPending || bulkResolveMutation.isPending;

  const candidatesLoading =
    candidatesPage.query.isLoading ||
    (candidatesPage.query.isFetching && stewardRows.length === 0);

  return (
    <Stack spacing={1.5} data-testid="cst-import-job-resolution-section">
      {(mappingStateQuery.data?.blocking_errors ?? []).length > 0 ? (
        <Alert severity="error" data-testid="cst-import-blocking-errors">
          {(mappingStateQuery.data?.blocking_errors ?? []).join(' · ')}
        </Alert>
      ) : null}
      {actionMsg ? (
        <Alert severity="success" onClose={() => setActionMsg(null)} data-testid="cst-import-action-msg">
          {actionMsg}
        </Alert>
      ) : null}
      {planApplySummary ? (
        <Alert severity={planApplySummary.severity} onClose={() => setPlanApplySummary(null)}>
          {planApplySummary.message}
        </Alert>
      ) : null}
      {candidatesPage.query.isError ? (
        <Alert severity="error" data-testid="cst-import-load-error">
          {safeDisplayError(candidatesPage.query.error)}
        </Alert>
      ) : null}

      <StewardResolutionPlanToolbar
        plan={{
          candidatesCount: filteredRows.length,
          readyCount: plan.readyPlanCandidateIds.length,
          suggestionsQuery: plan.suggestionsQuery,
        }}
        testIds={CST_IMPORT_ENGINE_CONFIG.planToolbarTestIds}
        copy={CST_IMPORT_ENGINE_CONFIG.planToolbarCopy}
        onApplyAllReady={() => plan.setApplyAllConfirmOpen(true)}
        applyAllPending={plan.applyResolutionPlan.isPending}
        applyAllDisabled={
          plan.readyPlanCandidateIds.length === 0 || plan.applyResolutionPlan.isPending
        }
        applyAllLabel={`Apply all ready (${plan.readyPlanCandidateIds.length})`}
        applyAllTestId="cst-resolution-plan-apply-all"
        summaryChipsSlot={planSummary ? cstPlanSummaryChips(planSummary) : undefined}
      />

      <Dialog
        open={plan.applyAllConfirmOpen}
        onClose={() => plan.setApplyAllConfirmOpen(false)}
        data-testid="cst-resolution-plan-apply-all-dialog"
      >
        <DialogTitle>Apply all ready rows?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            You are about to map <strong>{plan.readyPlanCandidateIds.length}</strong> ready token(s)
            — each to its own top suggestion target.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => plan.setApplyAllConfirmOpen(false)}>Cancel</Button>
          <StewardPendingButton
            variant="contained"
            pending={plan.applyResolutionPlan.isPending}
            pendingLabel="Applying…"
            onClick={() => {
              plan.setApplyAllConfirmOpen(false);
              void plan.applyResolutionPlan.mutateAsync(plan.readyPlanCandidateIds).catch(() => {});
            }}
            data-testid="cst-resolution-plan-apply-all-confirm"
          >
            Apply all ready
          </StewardPendingButton>
        </DialogActions>
      </Dialog>

      <StewardWorkspaceViewportShell
        rootTestId="cst-import-steward-viewport"
        bordered
        left={
          <ImportStewardCandidateWorkspace
            listDomainId={CST_IMPORT_STEWARD_CONFIG.listDomainId}
            importJobId={importJobId}
            copy={CST_IMPORT_STEWARD_CONFIG.listShellCopy}
            openRows={stewardRows}
            filteredRows={filteredRows}
            isLoading={candidatesLoading}
            busy={busy}
            embedded
            keepTableWhenFilterEmpty
            rootTestId="cst-import-candidate-workspace"
            filtersRegionTestId="cst-import-filters-region"
            actionFeedback={
              actionFeedback
                ? {
                    ...actionFeedback,
                    onDismiss: () => setActionFeedback(null),
                  }
                : null
            }
            columns={[
              {
                id: 'token',
                header: 'Token',
                cell: (r) => (
                  <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
                    {r.token}
                  </Typography>
                ),
              },
              {
                id: 'rows',
                header: 'Rows',
                align: 'right',
                cell: (r) => r.row_count,
              },
              {
                id: 'units',
                header: 'Units',
                align: 'right',
                cell: (r) => (r.total_units != null ? String(r.total_units) : '—'),
              },
              {
                id: 'status',
                header: 'Status',
                cell: (r) => <Chip size="small" label={r.status} />,
              },
              {
                id: 'top_suggestion',
                header: 'Top suggestion',
                cell: (r) => {
                  const top = r.suggestions?.[0];
                  if (!top) {
                    return (
                      <Typography variant="body2" color="text.secondary">
                        —
                      </Typography>
                    );
                  }
                  return (
                    <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
                        {top.label}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {r.match_reason ?? top.reason}
                      </Typography>
                    </Stack>
                  );
                },
              },
              {
                id: 'confidence',
                header: 'Confidence',
                align: 'right',
                cell: (r) => (
                  <ConfidenceBandCell score={r.confidence_score ?? r.suggestions?.[0]?.score} />
                ),
              },
              {
                id: 'actions',
                header: 'Actions',
                cell: (r) => (
                  <Button
                    size="small"
                    variant="text"
                    disabled={busy}
                    onClick={(e) => {
                      e.stopPropagation();
                      setDetailCandidate(r);
                    }}
                    data-testid={`cst-import-row-map-${r.id}`}
                  >
                    Map…
                  </Button>
                ),
              },
            ]}
            selection={workspaceSelection}
            onRowClick={(row) => setDetailCandidate(row)}
            getRowSx={(row) => {
              const selected = selectedIdSet.has(row.id);
              const drawerOpen = effectiveDetailCandidate?.id === row.id;
              if (selected || drawerOpen) {
                return { bgcolor: 'action.selected', cursor: 'pointer' };
              }
              return { cursor: 'pointer' };
            }}
            tabsSlot={
              <StewardEntityTabsBar
                tabs={CST_ENTITY_TAB_DEFS}
                activeTab={activeTab}
                onChange={setActiveTab}
                counts={counts}
                busy={busy}
                testIdPrefix="cst-import"
                ariaLabel="CST entity resolution"
                formatTabAriaLabel={formatCstEntityTabLabel}
              />
            }
            filtersSlot={
              <Stack spacing={1}>
                <StewardCandidateFilters
                  filters={activeFilters}
                  onChange={setActiveFilters}
                  visibleCount={filteredRows.length}
                  totalCount={candidatesPage.total}
                  hideEntityFilter
                  hidePartyFilter
                  hideProvisionalQueue
                  hideMatchToggles
                  clearToDefault={() => defaultCstFiltersForTab(activeTab)}
                  isAtDefault={(f) =>
                    f.queue === 'needs_review' && f.entity === activeTab && f.party === 'all'
                  }
                />
                <TextField
                  size="small"
                  label="Search tokens"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  data-testid="cst-import-search"
                />
              </Stack>
            }
            toolbarSlot={
              <Stack spacing={1} data-testid="cst-import-bulk-toolbar">
                <BulkSelectionToolbar
                  mode={bulkMode}
                  selectedCount={selectedIds.length}
                  visibleRowCount={filteredRows.length}
                  busy={busy}
                  onEnterSelectionMode={() => setBulkMode('selecting')}
                  onExitSelectionMode={() => {
                    setBulkMode('normal');
                    setSelectedIds([]);
                    setBulkEntityId('');
                  }}
                  onSelectAllVisible={() => setSelectedIds(visibleRowIds)}
                  onDeselectAll={() => setSelectedIds([])}
                  onPreviewDangerAction={() => undefined}
                  previewDangerLabel="Map selected"
                  previewDangerDisabled
                />
                {bulkMode === 'selecting' ? (
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <TextField
                      size="small"
                      label="Target entity id"
                      value={bulkEntityId}
                      onChange={(e) => setBulkEntityId(e.target.value)}
                      sx={{ width: 160 }}
                      data-testid="cst-import-bulk-entity-id"
                    />
                    <Button
                      size="small"
                      variant="contained"
                      disabled={busy || selectedIds.length === 0 || !bulkEntityId.trim()}
                      onClick={() => {
                        const entityId = Number(bulkEntityId);
                        if (!Number.isFinite(entityId) || entityId < 1) {
                          setActionFeedback({
                            message: 'Enter a valid target entity id for bulk map.',
                            severity: 'warning',
                          });
                          return;
                        }
                        void bulkResolveMutation.mutateAsync({
                          candidateIds: selectedIds,
                          entityId,
                        });
                      }}
                      data-testid="cst-import-bulk-map"
                    >
                      Map selected
                    </Button>
                  </Stack>
                ) : null}
                <StewardCandidatesPagination
                  page={candidatesPage.page}
                  pageCount={candidatesPage.pageCount}
                  pageSize={candidatesPage.pageSize}
                  total={candidatesPage.total}
                  skip={candidatesPage.skip}
                  pageItemCount={filteredRows.length}
                  busy={busy}
                  onPageChange={candidatesPage.setPage}
                  onPageSizeChange={candidatesPage.setPageSize}
                />
              </Stack>
            }
          />
        }
        drawer={
          effectiveDetailCandidate ? (
            <Box sx={{ p: 1.5, borderLeft: { md: '1px solid' }, borderColor: 'divider' }}>
              <CstCandidateStewardDrawer
                candidate={{
                  id: effectiveDetailCandidate.id,
                  import_job_id: importJobId,
                  entity_type: effectiveDetailCandidate.entity_type,
                  normalized_key: effectiveDetailCandidate.normalized_key,
                  row_count: effectiveDetailCandidate.row_count,
                  total_units: effectiveDetailCandidate.total_units,
                  sample_raw_values: effectiveDetailCandidate.sample_raw_values,
                  match_reason: effectiveDetailCandidate.match_reason,
                  confidence_score: effectiveDetailCandidate.confidence_score,
                  status: effectiveDetailCandidate.status,
                  context: effectiveDetailCandidate.context,
                  suggestions: effectiveDetailCandidate.suggestions,
                }}
                entity={activeTab}
                customerId={customerId}
                busy={busy}
                onClose={() => setDetailCandidate(null)}
                onResolve={async (entityId) => {
                  await resolveMutation.mutateAsync({
                    candidateId: effectiveDetailCandidate.id,
                    entityId,
                  });
                  setDetailCandidate(null);
                }}
                onIgnore={async () => {
                  await ignoreMutation.mutateAsync(effectiveDetailCandidate.id);
                  setDetailCandidate(null);
                }}
              />
            </Box>
          ) : (
            <Box sx={{ p: 2 }} data-testid="cst-import-drawer-empty">
              <Typography variant="body2" color="text.secondary">
                Select a token to review evidence and map a master.
              </Typography>
            </Box>
          )
        }
      />
    </Stack>
  );
}
