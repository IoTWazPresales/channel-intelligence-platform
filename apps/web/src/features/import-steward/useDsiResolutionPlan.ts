'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

import { registerClientBackgroundTask, finishClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';

import { notifyDsiAsyncPipelineStarted } from './dsiAsyncPipelineRun';
import { pollDsiResolutionPlanApplyTask, fetchDsiResolutionPlanApplyResultIfTerminal } from './dsiResolutionPlanApplyPoll';
import { pollDsiResolutionPlanComputeTask } from './dsiResolutionPlanComputePoll';
import { evictCandidatesFromResolutionPlanCache, removeCandidatesFromDsiCache } from './dsiStewardCacheUpdates';
import { DSI_STEWARD_CONFIG, invalidateDsiCatalogQueries, invalidateDsiImportJobStewardQueries, invalidateDsiStewardTabCounts } from './dsiSteward.config';
import type { DsiCatalogOpt, DsiPlanRowOverride, DsiUnresolvedGeoRowDto, PlanApplyFeedback } from './dsiSteward.types';
import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import { nextPlanScopeCandidateIds } from './dsiPlanScope';
import { summarizeApplyAllReadyProvisional } from './dsiResolutionPlanDisplay';
import { waitForDsiStewardBulkIdle } from './waitForDsiStewardBulkIdle';

export function useDsiResolutionPlan({
  importJobId,
  candidates,
  onInvalidate,
  onAsyncPipelineStarted,
  setSelectedIds,
  setPlanApplySummary,
}: {
  importJobId: number;
  candidates: DsiCandidateRow[];
  onInvalidate: () => void;
  /** Parent imports page: show validate-step progress panel + poll job/dsi-progress. */
  onAsyncPipelineStarted?: (args: { importJobId: number; taskId?: string | null }) => void;
  setSelectedIds: (ids: number[] | ((prev: number[]) => number[])) => void;
  setPlanApplySummary: (msg: PlanApplyFeedback | null) => void;
}) {
  const qc = useQueryClient();

  const [planRegionFallbackEnabled, setPlanRegionFallbackEnabled] = useState(false);
  const [planRegionId, setPlanRegionId] = useState('');
  const [planChannelId, setPlanChannelId] = useState('');
  const [resolutionPlan, setResolutionPlan] = useState<Record<string, unknown> | null>(null);
  const [suggestionDrawerId, setSuggestionDrawerId] = useState<number | null>(null);
  const [planOverrideMap, setPlanOverrideMap] = useState<Record<number, DsiPlanRowOverride>>({});
  const [planGlobalSuspicious, setPlanGlobalSuspicious] = useState(false);
  const planDebounceSkipRef = useRef(false);
  const planEvictSkipRef = useRef(false);
  const [planLoadToken, setPlanLoadToken] = useState(0);
  const [applyAllConfirmOpen, setApplyAllConfirmOpen] = useState(false);

  const { data: regions = [] } = useQuery({
    queryKey: DSI_STEWARD_CONFIG.catalogRegionsQueryKey(),
    queryFn: ({ signal }) => apiGet<DsiCatalogOpt[]>('/api/v1/catalog/regions', { signal }),
  });
  const { data: channels = [] } = useQuery({
    queryKey: DSI_STEWARD_CONFIG.catalogChannelsQueryKey(),
    queryFn: ({ signal }) => apiGet<DsiCatalogOpt[]>('/api/v1/catalog/channels', { signal }),
  });

  const unresolvedGeoQuery = useQuery({
    queryKey: DSI_STEWARD_CONFIG.unresolvedGeoTokensQueryKey(importJobId),
    enabled: importJobId > 0,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) =>
      apiGet<{ import_job_id: number; channels: DsiUnresolvedGeoRowDto[]; regions: DsiUnresolvedGeoRowDto[] }>(
        `/api/v1/mappings/import-jobs/${importJobId}/dsi-unresolved-geo-tokens`,
        { signal }
      ),
  });

  const planRegionFallbackKey = planRegionFallbackEnabled && planRegionId.trim() !== '' ? planRegionId : '';

  const planDefaultsBody = useCallback(
    () => ({
      default_region_id:
        planRegionFallbackEnabled &&
        planRegionId.trim() !== '' &&
        Number.isFinite(Number(planRegionId))
          ? Number(planRegionId)
          : null,
      default_channel_id:
        planChannelId.trim() !== '' && Number.isFinite(Number(planChannelId)) ? Number(planChannelId) : null,
    }),
    [planRegionFallbackEnabled, planRegionId, planChannelId]
  );

  const pageCandidateIds = useMemo(() => candidates.map((c) => c.id), [candidates]);

  /** Stable plan scope — do not shrink when steward actions optimistically remove rows from the page cache. */
  const [planScopeCandidateIds, setPlanScopeCandidateIds] = useState<number[]>([]);
  useEffect(() => {
    const current = pageCandidateIds;
    setPlanScopeCandidateIds((prev) => nextPlanScopeCandidateIds(prev, current));
  }, [pageCandidateIds]);

  const candidateIdsKey = useMemo(
    () => [...planScopeCandidateIds].sort((a, b) => a - b).join(','),
    [planScopeCandidateIds]
  );

  const suggestionsQuery = useQuery({
    queryKey: DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKey(
      importJobId,
      candidateIdsKey,
      planRegionFallbackKey,
      planChannelId
    ),
    enabled: importJobId > 0 && planScopeCandidateIds.length > 0,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    staleTime: 10 * 60 * 1000,
    queryFn: async ({ signal }) => {
      const body = { ...planDefaultsBody(), candidate_ids: planScopeCandidateIds };
      const enqueued = await apiPost<{
        import_job_id: number;
        task_id: string;
        async_poll?: boolean;
      }>(`/api/v1/mappings/import-jobs/${importJobId}/dsi-resolution-plan/compute-async`, body, {
        signal,
      });
      registerClientBackgroundTask({
        taskId: enqueued.task_id,
        importJobId,
        kind: 'dsi_resolution_plan_compute',
        label: `Computing resolution plan (DSI job ${importJobId})`,
      });
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
      try {
        return await pollDsiResolutionPlanComputeTask(importJobId, enqueued.task_id, {
          rowCount: planScopeCandidateIds.length,
          signal,
        });
      } finally {
        finishClientBackgroundTask(enqueued.task_id);
        void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
      }
    },
  });

  useEffect(() => {
    if (!suggestionsQuery.data) return;
    planDebounceSkipRef.current = true;
    setPlanOverrideMap({});
    setPlanGlobalSuspicious(false);
    setResolutionPlan(suggestionsQuery.data);
    setPlanLoadToken((n) => n + 1);
  }, [suggestionsQuery.data]);

  const overridesPayload = useCallback((): Array<Record<string, unknown>> => {
    return Object.entries(planOverrideMap).map(([cid, o]) => ({
      candidate_id: Number(cid),
      ...o,
    }));
  }, [planOverrideMap]);

  const patchPlanOverride = useCallback((candidateId: number, patch: DsiPlanRowOverride) => {
    setPlanOverrideMap((m) => ({
      ...m,
      [candidateId]: { ...m[candidateId], ...patch },
    }));
  }, []);

  const refreshPlanEffective = useMutation({
    mutationFn: async (args: { overrides: Array<Record<string, unknown>>; globalSuspicious: boolean }) =>
      apiPost<Record<string, unknown>>(`/api/v1/mappings/import-jobs/${importJobId}/dsi-resolution-plan/effective`, {
        ...planDefaultsBody(),
        candidate_ids: pageCandidateIds,
        confirm_for_suspicious_distributor_token: args.globalSuspicious,
        overrides: args.overrides,
      }),
    onSuccess: (data) => {
      setResolutionPlan(data);
    },
  });

  const refreshEffectiveAsyncRef = useRef(refreshPlanEffective.mutateAsync);
  refreshEffectiveAsyncRef.current = refreshPlanEffective.mutateAsync;

  useEffect(() => {
    if (planLoadToken === 0) return;
    if (planDebounceSkipRef.current) {
      planDebounceSkipRef.current = false;
      return;
    }
    if (planEvictSkipRef.current) {
      planEvictSkipRef.current = false;
      return;
    }
    const ovList = Object.entries(planOverrideMap).map(([cid, o]) => ({
      candidate_id: Number(cid),
      ...o,
    }));
    const t = window.setTimeout(() => {
      void refreshEffectiveAsyncRef
        .current({ overrides: ovList, globalSuspicious: planGlobalSuspicious })
        .catch(() => {});
    }, 450);
    return () => window.clearTimeout(t);
  }, [planOverrideMap, planGlobalSuspicious, planLoadToken]);

  const applyResolutionPlan = useMutation({
    mutationFn: async (args: {
      candidateIds: number[];
      overrides: Array<Record<string, unknown>>;
      globalSuspicious: boolean;
    }) => {
      await waitForDsiStewardBulkIdle(importJobId);
      let taskId: string | undefined;
      try {
        const body = {
          candidate_ids: args.candidateIds,
          ...planDefaultsBody(),
          partner_tier: 'unmanaged',
          provisional_notes_summary: null,
          confirm_for_suspicious_distributor_token: args.globalSuspicious,
          overrides: args.overrides.length ? args.overrides : null,
        };
        const enqueued = await apiPost<{
          import_job_id: number;
          task_id: string;
          async_poll?: boolean;
        }>(`/api/v1/mappings/import-jobs/${importJobId}/dsi-resolution-plan/apply-async`, body);
        taskId = enqueued.task_id;
        registerClientBackgroundTask({
          taskId: enqueued.task_id,
          importJobId,
          kind: 'dsi_resolution_plan_apply',
          label: `Applying resolution plan (DSI job ${importJobId})`,
        });
        void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
        try {
          return await pollDsiResolutionPlanApplyTask(importJobId, enqueued.task_id, {
            rowCount: args.candidateIds.length,
          });
        } catch (pollErr) {
          const late = await fetchDsiResolutionPlanApplyResultIfTerminal(importJobId, enqueued.task_id);
          if (late) return late;
          throw pollErr;
        }
      } finally {
        if (taskId) finishClientBackgroundTask(taskId);
        void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
      }
    },
    onSuccess: (data) => {
      const applied = Number(data.applied ?? 0);
      const failed = Number(data.failed ?? 0);
      const skippedHold = Number(data.skipped_hold ?? 0);
      const skippedNr = Number(data.skipped_not_ready ?? 0);
      const partial = Boolean(data.partial_success);
      const processed = Number(data.processed ?? applied);
      const interruptMsg = typeof data.error === 'string' ? data.error : '';
      const appliedIds = (Array.isArray(data.results) ? data.results : [])
        .filter((r) => r && typeof r === 'object' && (r as { status?: string }).status === 'applied')
        .map((r) => Number((r as { candidate_id?: unknown }).candidate_id))
        .filter((id) => Number.isFinite(id));

      if (appliedIds.length > 0) {
        removeCandidatesFromDsiCache(qc, importJobId, appliedIds);
        evictCandidatesFromResolutionPlanCache(qc, importJobId, appliedIds);
      }

      setPlanApplySummary({
        severity: partial ? 'warning' : 'success',
        message: partial
          ? `Resolution plan partially applied: ${applied} of ${processed} processed before interruption (${interruptMsg}). Failed ${failed}, skipped (hold) ${skippedHold}, skipped (not ready) ${skippedNr}. Refresh candidate counts and retry remaining rows.`
          : `Resolution plan: applied ${applied}, failed ${failed}, skipped (hold) ${skippedHold}, skipped (not ready) ${skippedNr}. Remaining rows are refreshing — re-run import validation (server) when you want staging updated.`,
      });
      if (!partial) {
        setSuggestionDrawerId(null);
        setPlanOverrideMap({});
        setPlanGlobalSuspicious(false);
        const appliedSet = new Set(appliedIds);
        setPlanScopeCandidateIds(
          candidates.map((c) => c.id).filter((id) => !appliedSet.has(id))
        );
        setPlanLoadToken((n) => (n === 0 ? 1 : n));
        for (const [, cached] of qc.getQueriesData<Record<string, unknown>>({
          queryKey: DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId),
        })) {
          if (cached && Array.isArray(cached.rows)) {
            setResolutionPlan(cached);
            break;
          }
        }
      }
      invalidateDsiImportJobStewardQueries(qc, importJobId, { includeImportJobsList: true });
      void qc.refetchQueries({
        queryKey: DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId),
      });
      setSelectedIds([]);
      onInvalidate();
    },
    onError: (err) => {
      setPlanApplySummary({
        severity: 'warning',
        message: `${safeDisplayError(err)} The worker may still be running — check the activity bell. When it finishes, refresh suggestions or reload the page to update counts.`,
      });
      invalidateDsiStewardTabCounts(qc, importJobId);
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId) });
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
    },
  });

  const dsiRevalidateFromServer = useMutation({
    mutationFn: async () => {
      const res = await apiPost<{
        ok: boolean;
        async?: boolean;
        import_job_id?: number;
        task_id?: string | null;
        message?: string;
      }>(
        `/api/v1/mappings/import-jobs/${importJobId}/revalidate-distributor-sales-inventory`,
        {}
      );
      if (res.async) {
        if (onAsyncPipelineStarted) {
          onAsyncPipelineStarted({ importJobId, taskId: res.task_id });
        } else {
          notifyDsiAsyncPipelineStarted(qc, importJobId, { taskId: res.task_id });
        }
      }
      return res;
    },
    onSuccess: (res) => {
      if (!res.async) {
        invalidateDsiImportJobStewardQueries(qc, importJobId, { includeImportJobsList: true });
        onInvalidate();
      }
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
    },
  });

  const planTableRows = useMemo(() => {
    const raw = resolutionPlan?.rows;
    if (!raw || !Array.isArray(raw)) return [];
    return raw as Array<Record<string, unknown>>;
  }, [resolutionPlan]);

  const applyAllProvisionalStats = useMemo(
    () => summarizeApplyAllReadyProvisional(planTableRows),
    [planTableRows]
  );

  const planByCandidateId = useMemo(() => {
    const m = new Map<number, Record<string, unknown>>();
    for (const r of planTableRows) {
      const id = Number(r.candidate_id);
      if (Number.isFinite(id)) m.set(id, r);
    }
    return m;
  }, [planTableRows]);

  const readyPlanCandidateIds = useMemo(() => {
    return planTableRows
      .filter(
        (r) =>
          r.ready === true &&
          r.duplicate_review_required !== true &&
          !(Array.isArray(r.resolution_blockers) &&
            (r.resolution_blockers as unknown[]).includes('duplicate_review_required'))
      )
      .map((r) => Number(r.candidate_id))
      .filter((id) => Number.isFinite(id));
  }, [planTableRows]);

  const planDrawerRow = useMemo(() => {
    if (suggestionDrawerId == null) return null;
    return planTableRows.find((r) => Number(r.candidate_id) === suggestionDrawerId) ?? null;
  }, [planTableRows, suggestionDrawerId]);

  const handleOpenSuggestionRow = useCallback((id: number | undefined) => {
    if (id != null) setSuggestionDrawerId(id);
  }, []);

  const invalidateGeoAndPlan = useCallback(() => {
    invalidateDsiImportJobStewardQueries(qc, importJobId);
    invalidateDsiCatalogQueries(qc);
    onInvalidate();
  }, [importJobId, onInvalidate, qc]);

  const evictResolvedCandidates = useCallback(
    (candidateIds: number[]) => {
      const ids = candidateIds.filter((id) => Number.isFinite(id));
      if (ids.length === 0) return;
      const idSet = new Set(ids);
      planEvictSkipRef.current = true;
      setPlanOverrideMap((m) => {
        const next = { ...m };
        for (const id of ids) delete next[id];
        return next;
      });
      setResolutionPlan((prev) => {
        if (!prev || !Array.isArray(prev.rows)) return prev;
        const rows = (prev.rows as Array<Record<string, unknown>>).filter(
          (r) => !idSet.has(Number(r.candidate_id))
        );
        const ready = rows.filter((r) => r.ready === true).length;
        const summary =
          prev.summary && typeof prev.summary === 'object'
            ? {
                ...(prev.summary as Record<string, unknown>),
                total: rows.length,
                ready,
                not_ready: rows.length - ready,
              }
            : prev.summary;
        return { ...prev, rows, summary };
      });
      evictCandidatesFromResolutionPlanCache(qc, importJobId, ids);
    },
    [importJobId, qc]
  );

  return {
    regions,
    channels,
    unresolvedGeoQuery,
    planRegionFallbackEnabled,
    setPlanRegionFallbackEnabled,
    planRegionId,
    setPlanRegionId,
    planChannelId,
    setPlanChannelId,
    resolutionPlan,
    suggestionDrawerId,
    setSuggestionDrawerId,
    planOverrideMap,
    planGlobalSuspicious,
    setPlanGlobalSuspicious,
    planLoadToken,
    applyAllConfirmOpen,
    setApplyAllConfirmOpen,
    suggestionsQuery,
    refreshPlanEffective,
    applyResolutionPlan,
    dsiRevalidateFromServer,
    overridesPayload,
    patchPlanOverride,
    planTableRows,
    applyAllProvisionalStats,
    planByCandidateId,
    readyPlanCandidateIds,
    planDrawerRow,
    handleOpenSuggestionRow,
    invalidateGeoAndPlan,
    evictResolvedCandidates,
  };
}
