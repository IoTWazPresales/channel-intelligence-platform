'use client';

import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';

import { DSI_ENGINE_CONFIG } from './dsiSteward.engineConfig';
import { useStewardBulkSteward } from './useStewardBulkSteward';

/** @deprecated Prefer {@link useStewardBulkSteward} with `DSI_ENGINE_CONFIG`. */
export function useDsiBulkSteward({
  importJobId,
  selectedIds,
  setSelectedIds,
  setBulkMode,
  onInvalidate,
  onBulkClosed,
  onApplyPlanFallback,
  applySuggestedRegion,
  onPlanRefresh,
  onEvictResolvedCandidates,
  onShrinkPlanScope,
}: {
  importJobId: number;
  selectedIds: number[];
  setSelectedIds: (ids: number[] | ((prev: number[]) => number[])) => void;
  setBulkMode: (mode: BulkTableSelectionMode) => void;
  onInvalidate: () => void;
  /** Called after successful apply or explicit cancel — return focus to toolbar. */
  onBulkClosed?: () => void;
  /** Client-only plan defaults (resolution suggestions), not steward API. */
  onApplyPlanFallback?: (args: {
    action: 'set_plan_fallback_region' | 'set_plan_fallback_channel';
    regionId: string;
    channelId: string;
  }) => Promise<void>;
  applySuggestedRegion?: (args: { candidateIds: number[] }) => Promise<void>;
  onPlanRefresh?: () => void | Promise<unknown>;
  onEvictResolvedCandidates?: (candidateIds: number[]) => void;
  onShrinkPlanScope?: (candidateIds: number[]) => void;
}) {
  return useStewardBulkSteward({
    importJobId,
    selectedIds,
    setSelectedIds,
    setBulkMode,
    onInvalidate,
    onBulkClosed,
    onApplyPlanFallback,
    applySuggestedRegion,
    onPlanRefresh,
    onEvictResolvedCandidates,
    onShrinkPlanScope,
    config: DSI_ENGINE_CONFIG,
  });
}
