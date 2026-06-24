'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiPost, safeDisplayError } from '@/lib/api';
import { registerClientBackgroundTask, finishClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';

import { pollShipmentBulkTask } from './shipmentBulkTaskPoll';
import { invalidateShipmentImportJobStewardQueries, SHIPMENT_STEWARD_CONFIG } from './shipmentSteward.config';
import type { InboundEvidenceMappingCandidateRow } from './inboundEvidenceMappingCandidateWorkspaceColumns';
import { nextPlanScopeCandidateIds } from './dsiPlanScope';

export type ShipmentPlanApplyFeedback = { severity: 'success' | 'warning' | 'error'; message: string };

export function useShipmentResolutionPlan({
  importJobId,
  candidates,
  onInvalidate,
  setSelectedIds,
  setPlanApplySummary,
}: {
  importJobId: number;
  candidates: InboundEvidenceMappingCandidateRow[];
  onInvalidate: () => void;
  setSelectedIds: (ids: number[] | ((prev: number[]) => number[])) => void;
  setPlanApplySummary: (msg: ShipmentPlanApplyFeedback | null) => void;
}) {
  const qc = useQueryClient();
  const [planScopeCandidateIds, setPlanScopeCandidateIds] = useState<number[]>([]);
  const [planOverrideMap, setPlanOverrideMap] = useState<Record<number, Record<string, unknown>>>({});
  const [applyAllConfirmOpen, setApplyAllConfirmOpen] = useState(false);

  const pageCandidateIds = useMemo(() => candidates.map((c) => c.id), [candidates]);
  useEffect(() => {
    setPlanScopeCandidateIds((prev) => nextPlanScopeCandidateIds(prev, pageCandidateIds));
  }, [pageCandidateIds]);

  const candidateIdsKey = useMemo(
    () => [...planScopeCandidateIds].sort((a, b) => a - b).join(','),
    [planScopeCandidateIds]
  );

  const suggestionsQuery = useQuery({
    queryKey: SHIPMENT_STEWARD_CONFIG.resolutionSuggestionsQueryKey(importJobId, candidateIdsKey),
    enabled: importJobId > 0 && planScopeCandidateIds.length > 0,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    staleTime: 10 * 60 * 1000,
    queryFn: async ({ signal }) => {
      const enqueued = await apiPost<{
        import_job_id: number;
        task_id: string;
        async_poll: boolean;
      }>(
        `/api/v1/shipment-evidence/import-jobs/${importJobId}/resolution-plan/compute-async`,
        { candidate_ids: planScopeCandidateIds },
        { signal }
      );
      if (!enqueued.async_poll) {
        return pollShipmentBulkTask<Record<string, unknown>>(importJobId, enqueued.task_id);
      }
      registerClientBackgroundTask({
        taskId: enqueued.task_id,
        importJobId,
        kind: 'shipment_bulk',
        label: 'Computing shipment resolution plan',
      });
      const polled = await pollShipmentBulkTask<Record<string, unknown>>(importJobId, enqueued.task_id);
      finishClientBackgroundTask(enqueued.task_id);
      return polled;
    },
  });

  const planByCandidateId = useMemo(() => {
    const map = new Map<number, Record<string, unknown>>();
    const rows = (suggestionsQuery.data?.rows as Record<string, unknown>[] | undefined) ?? [];
    for (const row of rows) {
      const cid = Number(row.candidate_id);
      if (Number.isFinite(cid)) map.set(cid, row);
    }
    return map;
  }, [suggestionsQuery.data]);

  const readyPlanCandidateIds = useMemo(
    () =>
      [...planByCandidateId.entries()]
        .filter(([, row]) => row.ready === true)
        .map(([id]) => id),
    [planByCandidateId]
  );

  const refreshSuggestions = useCallback(() => {
    void suggestionsQuery.refetch();
  }, [suggestionsQuery]);

  const applyResolutionPlan = useMutation({
    mutationFn: async (candidateIds: number[]) => {
      const overrides = candidateIds
        .map((id) => planOverrideMap[id])
        .filter(Boolean)
        .map((ov) => ({ candidate_id: ov!.candidate_id ?? 0, ...ov }));
      const enqueued = await apiPost<{
        import_job_id: number;
        task_id: string;
        async_poll: boolean;
      }>(`/api/v1/shipment-evidence/import-jobs/${importJobId}/resolution-plan/apply-async`, {
        candidate_ids: candidateIds,
        overrides,
      });
      if (!enqueued.async_poll) {
        return { result: await pollShipmentBulkTask<Record<string, unknown>>(importJobId, enqueued.task_id) };
      }
      registerClientBackgroundTask({
        taskId: enqueued.task_id,
        importJobId,
        kind: 'shipment_bulk',
        label: 'Applying shipment resolution plan',
      });
      const out = await pollShipmentBulkTask<Record<string, unknown>>(importJobId, enqueued.task_id);
      finishClientBackgroundTask(enqueued.task_id);
      return { result: out };
    },
    onSuccess: (polled, candidateIds) => {
      const result = polled.result as Record<string, unknown> | undefined;
      const applied = Number(result?.applied ?? 0);
      const failed = Number(result?.failed ?? 0);
      const skipped = Number(result?.skipped_not_ready ?? 0);
      if (applied > 0 && failed === 0) {
        setPlanApplySummary({ severity: 'success', message: `Applied ${applied} plan row(s).` });
      } else if (applied > 0) {
        setPlanApplySummary({
          severity: 'warning',
          message: `Partial success: applied ${applied}, failed ${failed}, skipped ${skipped}.`,
        });
      } else {
        setPlanApplySummary({
          severity: 'warning',
          message: `No rows applied (failed ${failed}, skipped ${skipped}).`,
        });
      }
      setSelectedIds([]);
      invalidateShipmentImportJobStewardQueries(qc, importJobId);
      onInvalidate();
      void suggestionsQuery.refetch();
    },
    onError: (err) => {
      setPlanApplySummary({ severity: 'error', message: safeDisplayError(err) });
    },
  });

  return {
    suggestionsQuery,
    planByCandidateId,
    readyPlanCandidateIds,
    refreshSuggestions,
    applyResolutionPlan,
    applyAllConfirmOpen,
    setApplyAllConfirmOpen,
    planOverrideMap,
    patchPlanOverride: (id: number, patch: Record<string, unknown>) => {
      setPlanOverrideMap((prev) => ({
        ...prev,
        [id]: { ...(prev[id] ?? { candidate_id: id }), candidate_id: id, ...patch },
      }));
    },
  };
}
