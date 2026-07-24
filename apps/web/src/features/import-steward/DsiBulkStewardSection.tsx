'use client';

import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';

import { DSI_ENGINE_CONFIG } from './dsiSteward.engineConfig';
import type { DsiCatalogOpt } from './dsiSteward.types';
import { StewardBulkSection } from './StewardBulkSection';
import type { useDsiBulkSteward } from './useDsiBulkSteward';
import type { useDsiResolutionPlan } from './useDsiResolutionPlan';

type BulkSteward = ReturnType<typeof useDsiBulkSteward>;
type PlanSteward = ReturnType<typeof useDsiResolutionPlan>;

/** @deprecated Prefer {@link StewardBulkSection} with engine config. */
export function DsiBulkStewardSection({
  bulkMode: _bulkMode,
  setBulkMode: _setBulkMode,
  selectedIds: _selectedIds,
  setSelectedIds: _setSelectedIds,
  displayedCandidateIds: _displayedCandidateIds,
  bulk,
  plan,
  regions: _regions,
  channels: _channels,
  stewardOverlayBusy: _stewardOverlayBusy,
}: {
  bulkMode: BulkTableSelectionMode;
  setBulkMode: (mode: BulkTableSelectionMode) => void;
  selectedIds: number[];
  setSelectedIds: (ids: number[] | ((prev: number[]) => number[])) => void;
  displayedCandidateIds: number[];
  bulk: BulkSteward;
  plan: PlanSteward;
  regions: DsiCatalogOpt[];
  channels: DsiCatalogOpt[];
  stewardOverlayBusy: boolean;
}) {
  return (
    <StewardBulkSection
      bulk={bulk}
      plan={plan}
      testIds={DSI_ENGINE_CONFIG.bulkTestIds}
      formatProposedLabel={DSI_ENGINE_CONFIG.formatBulkProposedLabel}
      formatAliasEvidence={DSI_ENGINE_CONFIG.formatBulkAliasEvidence}
    />
  );
}
