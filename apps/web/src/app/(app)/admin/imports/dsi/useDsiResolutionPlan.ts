'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';

import { DSI_ENGINE_CONFIG } from './dsiSteward.engineConfig';
import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import { DSI_STEWARD_CONFIG } from './dsiSteward.config';
import type { PlanApplyFeedback } from './dsiSteward.types';
import type {
  StewardCatalogOpt,
  StewardPlanApplyFeedback,
  StewardUnresolvedGeoRow,
} from '@/features/import-steward/stewardEngine.types';
import { useStewardResolutionPlan } from '@/features/import-steward/useStewardResolutionPlan';

/** DSI ready gate — duplicate_review is DSI-payload-only (shipment plan never emits it). */
export function dsiPlanRowIsReady(r: Record<string, unknown>): boolean {
  return (
    r.ready === true &&
    r.duplicate_review_required !== true &&
    !(
      Array.isArray(r.resolution_blockers) &&
      (r.resolution_blockers as unknown[]).includes('duplicate_review_required')
    )
  );
}

/**
 * DSI consumer #1 — composes geo catalogs, unresolved-geo, effective-plan refresh,
 * and suspicious confirm on top of the domain-neutral plan core.
 */
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
  onAsyncPipelineStarted?: (args: { importJobId: number; taskId?: string | null }) => void;
  setSelectedIds: (ids: number[] | ((prev: number[]) => number[])) => void;
  setPlanApplySummary: (msg: PlanApplyFeedback | null) => void;
}) {
  const qc = useQueryClient();
  const config = DSI_ENGINE_CONFIG;

  const [planRegionFallbackEnabled, setPlanRegionFallbackEnabled] = useState(false);
  const [planRegionId, setPlanRegionId] = useState('');
  const [planChannelId, setPlanChannelId] = useState('');
  const [planGlobalSuspicious, setPlanGlobalSuspicious] = useState(false);

  const { data: regions = [] } = useQuery({
    queryKey: config.catalogRegionsQueryKey(),
    queryFn: ({ signal }) => apiGet<StewardCatalogOpt[]>(config.catalogRegionsPath, { signal }),
  });
  const { data: channels = [] } = useQuery({
    queryKey: config.catalogChannelsQueryKey(),
    queryFn: ({ signal }) => apiGet<StewardCatalogOpt[]>(config.catalogChannelsPath, { signal }),
  });

  const unresolvedGeoQuery = useQuery({
    queryKey: config.unresolvedGeoTokensQueryKey(importJobId),
    enabled: importJobId > 0,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) =>
      apiGet<{ import_job_id: number; channels: StewardUnresolvedGeoRow[]; regions: StewardUnresolvedGeoRow[] }>(
        config.unresolvedGeoTokensPath(importJobId),
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

  const formatPlanApplySummary = useCallback((data: Record<string, unknown>): StewardPlanApplyFeedback => {
    const applied = Number(data.applied ?? 0);
    const failed = Number(data.failed ?? 0);
    const skippedHold = Number(data.skipped_hold ?? 0);
    const skippedNr = Number(data.skipped_not_ready ?? 0);
    const partial = Boolean(data.partial_success);
    const processed = Number(data.processed ?? applied);
    const interruptMsg = typeof data.error === 'string' ? data.error : '';
    return {
      severity: partial ? 'warning' : 'success',
      message: partial
        ? `Resolution plan partially applied: ${applied} of ${processed} processed before interruption (${interruptMsg}). Failed ${failed}, skipped (hold) ${skippedHold}, skipped (not ready) ${skippedNr}. Refresh candidate counts and retry remaining rows.`
        : `Resolution plan: applied ${applied}, failed ${failed}, skipped (hold) ${skippedHold}, skipped (not ready) ${skippedNr}. Remaining rows are refreshing — re-run import validation (server) when you want staging updated.`,
    };
  }, []);

  const core = useStewardResolutionPlan({
    importJobId,
    candidates,
    onInvalidate,
    onAsyncPipelineStarted,
    setSelectedIds,
    setPlanApplySummary: setPlanApplySummary as (msg: StewardPlanApplyFeedback | null) => void,
    config,
    suggestionsQueryKey: (candidateIdsKey) =>
      DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKey(
        importJobId,
        candidateIdsKey,
        planRegionFallbackKey,
        planChannelId
      ),
    buildComputeBody: (candidateIds) => ({
      ...planDefaultsBody(),
      candidate_ids: candidateIds,
    }),
    buildApplyBody: ({ candidateIds, overrides }) => ({
      candidate_ids: candidateIds,
      ...planDefaultsBody(),
      partner_tier: 'unmanaged',
      provisional_notes_summary: null,
      confirm_for_suspicious_distributor_token: planGlobalSuspicious,
      overrides: overrides.length ? overrides : null,
    }),
    readyRowFilter: dsiPlanRowIsReady,
    formatPlanApplySummary,
  });

  const {
    replaceResolutionPlan,
    planDebounceSkipRef,
    planEvictSkipRef,
    planLoadToken,
    planOverrideMap,
    overridesPayload,
  } = core;

  const pageCandidateIds = useMemo(() => candidates.map((c) => c.id), [candidates]);

  const refreshPlanEffective = useMutation({
    mutationFn: async (args: { overrides: Array<Record<string, unknown>>; globalSuspicious: boolean }) =>
      apiPost<Record<string, unknown>>(config.effectivePlanPath(importJobId), {
        ...planDefaultsBody(),
        candidate_ids: pageCandidateIds,
        confirm_for_suspicious_distributor_token: args.globalSuspicious,
        overrides: args.overrides,
      }),
    onSuccess: (data) => {
      replaceResolutionPlan(data);
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
  }, [
    planOverrideMap,
    planGlobalSuspicious,
    planLoadToken,
    planDebounceSkipRef,
    planEvictSkipRef,
  ]);

  // Clear suspicious with plan reset when suggestions refresh (core clears overrides; mirror DSI prior behavior)
  useEffect(() => {
    if (!core.suggestionsQuery.data) return;
    setPlanGlobalSuspicious(false);
  }, [core.suggestionsQuery.data]);

  const applyAllProvisionalStats = useMemo(
    () => config.summarizeApplyAllReadyProvisional(core.planTableRows),
    [config, core.planTableRows]
  );

  const invalidateGeoAndPlan = useCallback(() => {
    config.invalidateStewardQueries(qc, importJobId);
    config.invalidateCatalogQueries(qc);
    onInvalidate();
  }, [config, importJobId, onInvalidate, qc]);

  return {
    ...core,
    regions,
    channels,
    unresolvedGeoQuery,
    planRegionFallbackEnabled,
    setPlanRegionFallbackEnabled,
    planRegionId,
    setPlanRegionId,
    planChannelId,
    setPlanChannelId,
    planGlobalSuspicious,
    setPlanGlobalSuspicious,
    refreshPlanEffective,
    applyAllProvisionalStats,
    invalidateGeoAndPlan,
    /** @deprecated alias retained for call-site compatibility */
    dsiRevalidateFromServer: core.revalidateFromServer,
  };
}
