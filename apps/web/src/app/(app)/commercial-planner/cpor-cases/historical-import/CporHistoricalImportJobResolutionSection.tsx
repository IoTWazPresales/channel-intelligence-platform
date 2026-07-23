'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import { BulkSelectionToolbar } from '@/components/bulkTable/BulkSelectionToolbar';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import {
  confidenceBand,
  confidenceBandColor,
  confidenceBandLabel,
} from '@/features/import-steward/confidenceBand';
import { ImportStewardCandidateWorkspace } from '@/features/import-steward/ImportStewardCandidateWorkspace';
import { StewardCandidateFilters } from '@/features/import-steward/StewardCandidateFilters';
import { StewardEntityTabsBar, type StewardEntityTabCounts } from '@/features/import-steward/StewardEntityTabsBar';
import { StewardWorkspaceViewportShell } from '@/features/import-steward/StewardWorkspaceViewportShell';
import {
  defaultDsiStewardCandidateFilterState,
  type DsiStewardCandidateFilterState,
} from '@/features/import-steward/dsiStewardCandidateFilterLogic';
import { computeImportStewardSelectionHeaderState } from '@/features/import-steward/importStewardSelectionUtils';
import { safeDisplayError } from '@/lib/api';

import {
  CporCandidateStewardDrawer,
  type CporStewardRow,
} from './CporCandidateStewardDrawer';
import {
  bulkMapCporHistoricalTokens,
  cporDimLabel,
  cporTokenRowId,
  fetchCporDimOptions,
  fetchCporHistoricalCandidates,
  fetchCporHistoricalSummary,
  mapCporHistoricalToken,
  type CporDimPick,
} from './cporHistoricalImportApi';
import {
  CPOR_ENTITY_TAB_DEFS,
  CPOR_HISTORICAL_STEWARD_CONFIG,
  formatCporEntityTabLabel,
  invalidateCporHistoricalStewardQueries,
  type CporEntityTabId,
  type CporPlanClass,
} from './cporHistoricalSteward.config';

type CporEntityTabCounts = StewardEntityTabCounts<CporEntityTabId>;

function emptyCounts(): CporEntityTabCounts {
  return {
    product: { total: null, needsWork: null },
    customer: { total: null, needsWork: null },
    distributor: { total: null, needsWork: null },
  };
}

function defaultCporFiltersForTab(tab: CporEntityTabId): DsiStewardCandidateFilterState {
  return {
    ...defaultDsiStewardCandidateFilterState(),
    entity: tab,
    party: 'all',
  };
}

/** Drive queue chips from Unit 1 plan_class — no inert DSI-only queues. */
function filterCporStewardRows(
  rows: CporStewardRow[],
  filters: DsiStewardCandidateFilterState,
  search: string
): CporStewardRow[] {
  let next = rows;
  const queue = filters.queue;
  if (queue === 'ready_to_map') {
    next = next.filter((r) => r.plan_class === 'ready_to_map');
  } else if (queue === 'ambiguous_eligible') {
    next = next.filter((r) => r.plan_class === 'ambiguous_eligible');
  } else if (queue === 'no_match') {
    next = next.filter((r) => r.plan_class === 'no_match');
  } else if (queue === 'needs_review') {
    next = next.filter((r) => r.plan_class === 'needs_review');
  } else if (queue === 'provisional') {
    // CPOR has no provisional masters — keep empty rather than invent semantics.
    next = [];
  }
  if (!search) return next;
  const needle = search.toLowerCase();
  return next.filter(
    (r) =>
      r.token.toLowerCase().includes(needle) ||
      r.status.toLowerCase().includes(needle) ||
      String(r.plan_class ?? '').toLowerCase().includes(needle) ||
      String(r.match_reason ?? '').toLowerCase().includes(needle) ||
      (r.suggestions ?? []).some((s) => s.label.toLowerCase().includes(needle)) ||
      String(r.row_count).includes(needle)
  );
}

function ConfidenceBandCell({ score }: { score: number | null }) {
  const band = confidenceBand(score);
  if (band == null) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="cpor-historical-confidence-empty">
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
        data-testid="cpor-historical-confidence-band"
      />
      <Typography variant="caption" color="text.secondary">
        {Number(score).toFixed(2)}
      </Typography>
    </Stack>
  );
}


export function CporHistoricalImportJobResolutionSection({
  importJobId,
  pipelineRunning = false,
  onInvalidate: onInvalidateProp,
  onAsyncPipelineStarted,
}: {
  importJobId: number | null;
  pipelineRunning?: boolean;
  onInvalidate?: () => void;
  onAsyncPipelineStarted?: (args: { importJobId: number; taskId?: string | null }) => void;
}) {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<CporEntityTabId>('product');
  const [activeFilters, setActiveFilters] = useState<DsiStewardCandidateFilterState>(() =>
    defaultCporFiltersForTab('product')
  );
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkMode, setBulkMode] = useState<BulkTableSelectionMode>('normal');
  const [bulkTarget, setBulkTarget] = useState<CporDimPick | null>(null);
  const [detailCandidate, setDetailCandidate] = useState<CporStewardRow | null>(null);
  const [actionFeedback, setActionFeedback] = useState<{
    message: string;
    severity: 'error' | 'warning';
  } | null>(null);
  const workspaceToolbarRef = useRef<HTMLDivElement | null>(null);

  const tabbedMode = importJobId != null;

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const onInvalidate = useCallback(() => {
    if (importJobId == null) return;
    invalidateCporHistoricalStewardQueries(qc, importJobId);
    onInvalidateProp?.();
  }, [importJobId, onInvalidateProp, qc]);

  const summaryQuery = useQuery({
    queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.summaryQueryKey(importJobId ?? 0),
    enabled: tabbedMode,
    queryFn: ({ signal }) => fetchCporHistoricalSummary(importJobId!, signal),
  });

  const candidatesQuery = useQuery({
    queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.candidatesQueryKey(importJobId ?? 0, activeTab),
    enabled: tabbedMode,
    queryFn: ({ signal }) => fetchCporHistoricalCandidates(importJobId!, activeTab, signal),
  });

  const stewardRows: CporStewardRow[] = useMemo(
    () =>
      (candidatesQuery.data?.candidates ?? []).map((c) => ({
        id: cporTokenRowId(c.token),
        entity_type: c.entity,
        normalized_key: c.token,
        token: c.token,
        row_count: c.row_count,
        total_units: null,
        total_reported_value: null,
        sample_raw_values: [c.token],
        status: c.status,
        match_reason: c.match_reason ?? null,
        confidence_score: c.confidence ?? null,
        context: null,
        plan_class: (c.plan_class as CporPlanClass | null | undefined) ?? null,
        suggestions: c.suggestions ?? [],
      })),
    [candidatesQuery.data?.candidates]
  );

  const filteredRows = useMemo(
    () => filterCporStewardRows(stewardRows, activeFilters, debouncedSearch),
    [stewardRows, activeFilters, debouncedSearch]
  );

  const counts: CporEntityTabCounts = useMemo(() => {
    const unresolved = summaryQuery.data?.unresolved_counts;
    const fromCandidates = candidatesQuery.data?.counts;
    const next = emptyCounts();
    for (const id of ['product', 'customer', 'distributor'] as const) {
      const n = unresolved?.[id] ?? fromCandidates?.[id] ?? null;
      next[id] = { total: n, needsWork: n != null && n > 0 ? n : 0 };
    }
    return next;
  }, [summaryQuery.data?.unresolved_counts, candidatesQuery.data?.counts]);

  const planClassCountsForTab = useMemo(() => {
    const fromSummary = summaryQuery.data?.plan_class_counts?.[activeTab];
    const fromCandidates = candidatesQuery.data?.plan_class_counts?.[activeTab];
    return fromSummary ?? fromCandidates ?? {};
  }, [
    activeTab,
    summaryQuery.data?.plan_class_counts,
    candidatesQuery.data?.plan_class_counts,
  ]);

  const productMatchStatusCounts = useMemo(
    () => ({
      no_match: planClassCountsForTab.no_match,
      ambiguous_eligible: planClassCountsForTab.ambiguous_eligible,
    }),
    [planClassCountsForTab]
  );

  useEffect(() => {
    setDetailCandidate(null);
    setSelectedIds([]);
    setBulkMode('normal');
    setBulkTarget(null);
    setSearchInput('');
    setDebouncedSearch('');
    setActiveFilters(defaultCporFiltersForTab(activeTab));
  }, [importJobId, activeTab]);

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

  const mapMutation = useMutation({
    mutationFn: async (args: { tokens: string[]; dimId: number }) => {
      if (importJobId == null) throw new Error('No import job');
      if (args.tokens.length === 1) {
        return mapCporHistoricalToken({
          jobId: importJobId,
          entity: activeTab,
          token: args.tokens[0]!,
          dimId: args.dimId,
        });
      }
      return bulkMapCporHistoricalTokens({
        jobId: importJobId,
        entity: activeTab,
        tokens: args.tokens,
        dimId: args.dimId,
      });
    },
    onSuccess: () => {
      setActionFeedback(null);
      setSelectedIds([]);
      setBulkMode('normal');
      setBulkTarget(null);
      onInvalidate();
      onAsyncPipelineStarted?.({ importJobId: importJobId!, taskId: null });
    },
    onError: (e) => {
      setActionFeedback({ message: safeDisplayError(e), severity: 'error' });
    },
  });

  const stewardOverlayBusy = mapMutation.isPending || pipelineRunning;
  const candidatesLoading =
    candidatesQuery.isLoading || (candidatesQuery.isFetching && stewardRows.length === 0);

  const fetchBulkOptions = useCallback(
    (q: string, signal: AbortSignal) => fetchCporDimOptions(activeTab, q, signal),
    [activeTab]
  );

  const selectedTokens = useMemo(() => {
    const byId = new Map(stewardRows.map((r) => [r.id, r.token]));
    return selectedIds.map((id) => byId.get(id)).filter((t): t is string => Boolean(t));
  }, [selectedIds, stewardRows]);

  const openBulkMap = useCallback(() => {
    setBulkMode('selecting');
    if (selectedIds.length === 0 && filteredRows.length > 0) {
      setSelectedIds(filteredRows.map((r) => r.id));
    }
  }, [filteredRows, selectedIds.length]);

  if (importJobId == null) {
    return (
      <Alert severity="info" data-testid="cpor-historical-import-job-resolution-section">
        Upload and validate a CPOR historical workbook to load unresolved tokens.
      </Alert>
    );
  }

  const drawer =
    effectiveDetailCandidate != null ? (
      <CporCandidateStewardDrawer
        candidate={effectiveDetailCandidate}
        entity={activeTab}
        busy={stewardOverlayBusy}
        onClose={() => setDetailCandidate(null)}
        onMap={async ({ token, dimId }) => {
          await mapMutation.mutateAsync({ tokens: [token], dimId });
        }}
      />
    ) : null;

  return (
    <Stack spacing={2} data-testid="cpor-historical-import-job-resolution-section">
      {summaryQuery.data ? (
        <Alert severity="info" data-testid="cpor-historical-steward-case-counts">
          Job {summaryQuery.data.id} · {summaryQuery.data.cases_ready} case(s) ready ·{' '}
          {summaryQuery.data.cases_blocked} blocked · {summaryQuery.data.staging_count} staging rows
        </Alert>
      ) : null}

      <StewardWorkspaceViewportShell
        bordered
        rootTestId="cpor-historical-steward-workspace-viewport-shell"
        left={
          <Box sx={{ flex: 1, minHeight: 0, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <ImportStewardCandidateWorkspace
              embedded
              keepTableWhenFilterEmpty
              rootTestId="cpor-historical-steward-candidate-workspace"
              listDomainId={CPOR_HISTORICAL_STEWARD_CONFIG.listDomainId}
              importJobId={importJobId}
              copy={CPOR_HISTORICAL_STEWARD_CONFIG.listShellCopy}
              openRows={stewardRows}
              filteredRows={filteredRows}
              isLoading={candidatesLoading}
              busy={stewardOverlayBusy}
              busyOverlay={{
                message: mapMutation.isPending ? 'Mapping tokens…' : 'Pipeline running…',
              }}
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
                  id: 'plan_class',
                  header: 'Plan class',
                  cell: (r) =>
                    r.plan_class ? (
                      <Chip size="small" label={String(r.plan_class).replace(/_/g, ' ')} />
                    ) : (
                      '—'
                    ),
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
                  cell: (r) => <ConfidenceBandCell score={r.confidence_score} />,
                },
                {
                  id: 'actions',
                  header: 'Actions',
                  cell: (r) => (
                    <Button
                      size="small"
                      variant="text"
                      disabled={stewardOverlayBusy}
                      onClick={(e) => {
                        e.stopPropagation();
                        setDetailCandidate(r);
                      }}
                      data-testid={`cpor-historical-row-map-${r.id}`}
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
                  tabs={CPOR_ENTITY_TAB_DEFS}
                  activeTab={activeTab}
                  onChange={setActiveTab}
                  counts={counts}
                  busy={stewardOverlayBusy}
                  testIdPrefix="cpor-historical"
                  ariaLabel="CPOR historical entity resolution"
                  formatTabAriaLabel={formatCporEntityTabLabel}
                />
              }
              filtersSlot={
                <Stack spacing={1.5}>
                  <StewardCandidateFilters
                    filters={activeFilters}
                    onChange={setActiveFilters}
                    visibleCount={filteredRows.length}
                    totalCount={stewardRows.length}
                    hideEntityFilter
                    hidePartyFilter
                    hideProvisionalQueue
                    hideMatchToggles
                    showProductMatchStatusChips
                    productMatchStatusCounts={productMatchStatusCounts}
                    clearToDefault={() => defaultCporFiltersForTab(activeTab)}
                    isAtDefault={(filters) => {
                      const def = defaultCporFiltersForTab(activeTab);
                      return filters.queue === def.queue && filters.entity === def.entity;
                    }}
                  />
                  <TextField
                    size="small"
                    fullWidth
                    label="Search tokens"
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    placeholder="Refine by token, status, or row count"
                    disabled={stewardOverlayBusy}
                    data-testid="cpor-historical-steward-search"
                  />
                </Stack>
              }
              toolbarSlot={
                <Stack
                  ref={workspaceToolbarRef}
                  direction="row"
                  spacing={1}
                  alignItems="center"
                  flexWrap="wrap"
                  useFlexGap
                >
                  {bulkMode === 'selecting' ? (
                    <BulkSelectionToolbar
                      mode={bulkMode}
                      selectedCount={selectedIds.length}
                      visibleRowCount={filteredRows.length}
                      onEnterSelectionMode={() => setBulkMode('selecting')}
                      onExitSelectionMode={() => {
                        setBulkMode('normal');
                        setSelectedIds([]);
                        setBulkTarget(null);
                        workspaceToolbarRef.current?.querySelector<HTMLElement>('button')?.focus();
                      }}
                      onSelectAllVisible={() => setSelectedIds(filteredRows.map((r) => r.id))}
                      onDeselectAll={() => setSelectedIds([])}
                      busy={mapMutation.isPending}
                      previewDangerLabel="Map selected"
                      previewDangerDisabled={
                        selectedIds.length === 0 || !bulkTarget || mapMutation.isPending
                      }
                      onPreviewDangerAction={() => {
                        if (!bulkTarget || selectedTokens.length === 0) return;
                        void mapMutation.mutateAsync({
                          tokens: selectedTokens,
                          dimId: bulkTarget.id,
                        });
                      }}
                    />
                  ) : (
                    <>
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={filteredRows.length === 0 && selectedIds.length === 0}
                        onClick={openBulkMap}
                        data-testid="cpor-historical-bulk-map-open"
                      >
                        Map selected to…
                      </Button>
                      <Typography variant="caption" color="text.secondary">
                        {selectedIds.length} selected · Click a row to map one token
                      </Typography>
                      <Box sx={{ flexGrow: 1 }} />
                    </>
                  )}
                </Stack>
              }
              bulkFormSlot={
                bulkMode === 'selecting' ? (
                  <Box sx={{ maxWidth: 420 }} data-testid="cpor-historical-bulk-map-form">
                    <EntitySearchAutocomplete<CporDimPick>
                      label={`Map selected ${activeTab} tokens to…`}
                      value={bulkTarget}
                      onChange={setBulkTarget}
                      fetchOptions={fetchBulkOptions}
                      getOptionLabel={cporDimLabel}
                      disabled={stewardOverlayBusy}
                      helperText={
                        selectedTokens.length
                          ? `${selectedTokens.length} token(s) will receive this mapping`
                          : 'Select tokens first'
                      }
                    />
                  </Box>
                ) : null
              }
            />
          </Box>
        }
        drawer={drawer}
      />
    </Stack>
  );
}
