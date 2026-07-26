'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { QueryKey } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiPost, safeDisplayError } from '@/lib/api';

import { registerClientBackgroundTask, finishClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';

import { nextPlanScopeCandidateIds, shrinkPlanScopeCandidateIds } from './stewardPlanScope';
import type {
  StewardEngineCandidateRow,
  StewardPlanApplyFeedback,
  StewardPlanEngineConfig,
  StewardPlanRowOverride,
} from './stewardEngine.types';

/** Canonical apply signature — consumers adapt at their wrapper; core has one entry. */
export type StewardApplyResolutionPlanArgs = number[];

const defaultReadyRow = (r: Record<string, unknown>) => r.ready === true;

export function useStewardResolutionPlan({
  importJobId,
  candidates,
  onInvalidate,
  onAsyncPipelineStarted,
  setSelectedIds,
  setPlanApplySummary,
  config,
  suggestionsQueryKey,
  buildComputeBody,
  buildApplyBody,
  readyRowFilter = defaultReadyRow,
  formatPlanApplySummary,
}: {
  importJobId: number;
  candidates: StewardEngineCandidateRow[];
  onInvalidate: () => void;
  onAsyncPipelineStarted?: (args: { importJobId: number; taskId?: string | null }) => void;
  setSelectedIds: (ids: number[] | ((prev: number[]) => number[])) => void;
  setPlanApplySummary: (msg: StewardPlanApplyFeedback | null) => void;
  config: StewardPlanEngineConfig;
  /** Override when consumer needs extra key parts (e.g. DSI region/channel). */
  suggestionsQueryKey?: (candidateIdsKey: string) => QueryKey;
  buildComputeBody?: (candidateIds: number[]) => Record<string, unknown>;
  buildApplyBody?: (args: {
    candidateIds: number[];
    overrides: Array<Record<string, unknown>>;
  }) => Record<string, unknown>;
  /** Domain ready gate. Default: ready === true. DSI composes duplicate_review on top. */
  readyRowFilter?: (row: Record<string, unknown>) => boolean;
  formatPlanApplySummary?: (data: Record<string, unknown>) => StewardPlanApplyFeedback;
}) {
  const qc = useQueryClient();

  const [resolutionPlan, setResolutionPlan] = useState<Record<string, unknown> | null>(null);
  const [suggestionDrawerId, setSuggestionDrawerId] = useState<number | null>(null);
  const [planOverrideMap, setPlanOverrideMap] = useState<Record<number, StewardPlanRowOverride>>({});
  const planDebounceSkipRef = useRef(false);
  const planEvictSkipRef = useRef(false);
  const [planLoadToken, setPlanLoadToken] = useState(0);
  const [applyAllConfirmOpen, setApplyAllConfirmOpen] = useState(false);

  const pageCandidateIds = useMemo(() => candidates.map((c) => c.id), [candidates]);

  const [planScopeCandidateIds, setPlanScopeCandidateIds] = useState<number[]>([]);
  useEffect(() => {
    const current = pageCandidateIds;
    setPlanScopeCandidateIds((prev) => nextPlanScopeCandidateIds(prev, current));
  }, [pageCandidateIds]);

  const shrinkPlanScope = useCallback((removedIds: number[]) => {
    setPlanScopeCandidateIds((prev) => shrinkPlanScopeCandidateIds(prev, removedIds));
  }, []);

  const candidateIdsKey = useMemo(
    () => [...planScopeCandidateIds].sort((a, b) => a - b).join(','),
    [planScopeCandidateIds]
  );

  const resolvedSuggestionsKey = useMemo(
    () =>
      suggestionsQueryKey
        ? suggestionsQueryKey(candidateIdsKey)
        : config.resolutionSuggestionsQueryKey(importJobId, candidateIdsKey),
    [suggestionsQueryKey, config, importJobId, candidateIdsKey]
  );

  const suggestionsQuery = useQuery({
    queryKey: resolvedSuggestionsKey,
    enabled: importJobId > 0 && planScopeCandidateIds.length > 0,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    staleTime: 10 * 60 * 1000,
    queryFn: async ({ signal }) => {
      const body = buildComputeBody
        ? buildComputeBody(planScopeCandidateIds)
        : { candidate_ids: planScopeCandidateIds };
      const enqueued = await apiPost<{
        import_job_id: number;
        task_id: string;
        async_poll?: boolean;
      }>(config.computePlanAsyncPath(importJobId), body, {
        signal,
      });
      registerClientBackgroundTask({
        taskId: enqueued.task_id,
        importJobId,
        kind: config.computeBackgroundKind as never,
        label: config.computeBackgroundLabel(importJobId),
      });
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
      try {
        return await config.pollComputeTask(importJobId, enqueued.task_id, {
          rowCount: planScopeCandidateIds.length,
          signal,
        });
      } finally {
        finishClientBackgroundTask(enqueued.task_id);
        void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
      }
    },
  });

  const refreshSuggestions = useCallback(() => suggestionsQuery.refetch(), [suggestionsQuery]);

  useEffect(() => {
    if (!suggestionsQuery.data) return;
    planDebounceSkipRef.current = true;
    setPlanOverrideMap({});
    setResolutionPlan(suggestionsQuery.data);
    setPlanLoadToken((n) => n + 1);
  }, [suggestionsQuery.data]);

  const replaceResolutionPlan = useCallback((data: Record<string, unknown>) => {
    setResolutionPlan(data);
  }, []);

  const overridesPayload = useCallback((): Array<Record<string, unknown>> => {
    return Object.entries(planOverrideMap).map(([cid, o]) => ({
      candidate_id: Number(cid),
      ...o,
    }));
  }, [planOverrideMap]);

  const patchPlanOverride = useCallback((candidateId: number, patch: StewardPlanRowOverride) => {
    setPlanOverrideMap((m) => ({
      ...m,
      [candidateId]: { ...m[candidateId], ...patch },
    }));
  }, []);

  /** Canonical apply: candidate id list only. Body extras via buildApplyBody composition. */
  const applyResolutionPlan = useMutation({
    mutationFn: async (candidateIds: StewardApplyResolutionPlanArgs) => {
      await config.waitForBulkIdle(importJobId);
      const overrides = overridesPayload();
      let taskId: string | undefined;
      try {
        const body = buildApplyBody
          ? buildApplyBody({ candidateIds, overrides })
          : {
              candidate_ids: candidateIds,
              overrides: overrides.length ? overrides : null,
            };
        const enqueued = await apiPost<{
          import_job_id: number;
          task_id: string;
          async_poll?: boolean;
        }>(config.applyPlanAsyncPath(importJobId), body);
        taskId = enqueued.task_id;
        registerClientBackgroundTask({
          taskId: enqueued.task_id,
          importJobId,
          kind: config.applyBackgroundKind as never,
          label: config.applyBackgroundLabel(importJobId),
        });
        void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
        try {
          return await config.pollApplyTask(importJobId, enqueued.task_id, {
            rowCount: candidateIds.length,
          });
        } catch (pollErr) {
          const late = await config.fetchApplyResultIfTerminal(importJobId, enqueued.task_id);
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

      if (!partial && appliedIds.length > 0) {
        config.removeCandidatesFromCache(qc, importJobId, appliedIds);
        config.evictCandidatesFromPlanCache(qc, importJobId, appliedIds);
      }

      if (formatPlanApplySummary) {
        setPlanApplySummary(formatPlanApplySummary(data));
      } else {
        setPlanApplySummary({
          severity: partial ? 'warning' : 'success',
          message: partial
            ? `Resolution plan partially applied: ${applied} of ${processed} processed before interruption (${interruptMsg}). Failed ${failed}, skipped (hold) ${skippedHold}, skipped (not ready) ${skippedNr}. Refresh candidate counts and retry remaining rows.`
            : `Resolution plan: applied ${applied}, failed ${failed}, skipped (hold) ${skippedHold}, skipped (not ready) ${skippedNr}. Remaining rows are refreshing — re-run import validation (server) when you want staging updated.`,
        });
      }
      if (!partial) {
        setSuggestionDrawerId(null);
        setPlanOverrideMap({});
        const appliedSet = new Set(appliedIds);
        setPlanScopeCandidateIds(
          candidates.map((c) => c.id).filter((id) => !appliedSet.has(id))
        );
        setPlanLoadToken((n) => (n === 0 ? 1 : n));
        for (const [, cached] of qc.getQueriesData<Record<string, unknown>>({
          queryKey: config.resolutionSuggestionsQueryKeyPrefix(importJobId),
        })) {
          if (cached && Array.isArray(cached.rows)) {
            setResolutionPlan(cached);
            break;
          }
        }
      }
      config.invalidateStewardQueries(qc, importJobId, { includeImportJobsList: true });
      void qc.refetchQueries({
        queryKey: config.resolutionSuggestionsQueryKeyPrefix(importJobId),
      });
      setSelectedIds([]);
      onInvalidate();
    },
    onError: (err) => {
      setPlanApplySummary({
        severity: 'warning',
        message: `${safeDisplayError(err)} The worker may still be running — check the activity bell. When it finishes, refresh suggestions or reload the page to update counts.`,
      });
      config.invalidateTabCounts(qc, importJobId);
      void qc.invalidateQueries({ queryKey: config.candidatesQueryKey(importJobId) });
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
    },
  });

  const revalidateFromServer = useMutation({
    mutationFn: async () => {
      const res = await apiPost<{
        ok: boolean;
        async?: boolean;
        import_job_id?: number;
        task_id?: string | null;
        message?: string;
      }>(config.revalidatePath(importJobId), {});
      if (res.async) {
        if (onAsyncPipelineStarted) {
          onAsyncPipelineStarted({ importJobId, taskId: res.task_id });
        } else {
          config.notifyAsyncPipelineStarted(qc, importJobId, { taskId: res.task_id });
        }
      }
      return res;
    },
    onSuccess: (res) => {
      if (!res.async) {
        config.invalidateStewardQueries(qc, importJobId, { includeImportJobsList: true });
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
      .filter(readyRowFilter)
      .map((r) => Number(r.candidate_id))
      .filter((id) => Number.isFinite(id));
  }, [planTableRows, readyRowFilter]);

  const planDrawerRow = useMemo(() => {
    if (suggestionDrawerId == null) return null;
    return planTableRows.find((r) => Number(r.candidate_id) === suggestionDrawerId) ?? null;
  }, [planTableRows, suggestionDrawerId]);

  const handleOpenSuggestionRow = useCallback((id: number | undefined) => {
    if (id != null) setSuggestionDrawerId(id);
  }, []);

  const evictResolvedCandidates = useCallback(
    (candidateIds: number[]) => {
      const ids = candidateIds.filter((id) => Number.isFinite(id));
      if (ids.length === 0) return;
      const idSet = new Set(ids);
      setPlanScopeCandidateIds((prev) => shrinkPlanScopeCandidateIds(prev, ids));
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
      config.evictCandidatesFromPlanCache(qc, importJobId, ids);
    },
    [config, importJobId, qc]
  );

  return {
    resolutionPlan,
    replaceResolutionPlan,
    suggestionDrawerId,
    setSuggestionDrawerId,
    planOverrideMap,
    planLoadToken,
    planDebounceSkipRef,
    planEvictSkipRef,
    applyAllConfirmOpen,
    setApplyAllConfirmOpen,
    suggestionsQuery,
    applyResolutionPlan,
    revalidateFromServer,
    overridesPayload,
    patchPlanOverride,
    planTableRows,
    planByCandidateId,
    readyPlanCandidateIds,
    planDrawerRow,
    handleOpenSuggestionRow,
    evictResolvedCandidates,
    shrinkPlanScope,
    refreshSuggestions,
  };
}
