'use client';

import { DSI_ENGINE_CONFIG } from './dsiSteward.engineConfig';
import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import type { PlanApplyFeedback } from './dsiSteward.types';
import { useStewardResolutionPlan } from './useStewardResolutionPlan';

/** @deprecated Prefer {@link useStewardResolutionPlan} with `DSI_ENGINE_CONFIG`. */
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
  const plan = useStewardResolutionPlan({
    importJobId,
    candidates,
    onInvalidate,
    onAsyncPipelineStarted,
    setSelectedIds,
    setPlanApplySummary,
    config: DSI_ENGINE_CONFIG,
  });
  return {
    ...plan,
    /** @deprecated alias retained for call-site compatibility */
    dsiRevalidateFromServer: plan.revalidateFromServer,
  };
}
