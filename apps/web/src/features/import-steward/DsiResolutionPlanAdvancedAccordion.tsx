'use client';

import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query';

import type { DsiCatalogOpt, DsiUnresolvedGeoRowDto } from './dsiSteward.types';
import { DsiResolutionPlanToolbar } from './DsiResolutionPlanToolbar';
import { DsiRegionChannelTabPanel } from './DsiRegionChannelTabPanel';

type PlanHookSlice = {
  importJobId: number;
  candidatesCount: number;
  regions: DsiCatalogOpt[];
  channels: DsiCatalogOpt[];
  unresolvedGeoQuery: UseQueryResult<{
    import_job_id: number;
    channels: DsiUnresolvedGeoRowDto[];
    regions: DsiUnresolvedGeoRowDto[];
  }>;
  resolutionPlan: Record<string, unknown> | null;
  planGlobalSuspicious: boolean;
  setPlanGlobalSuspicious: (v: boolean) => void;
  planLoadToken: number;
  planTableRows: Array<Record<string, unknown>>;
  suggestionsQuery: UseQueryResult<Record<string, unknown>>;
  refreshPlanEffective: UseMutationResult<
    Record<string, unknown>,
    Error,
    { overrides: Array<Record<string, unknown>>; globalSuspicious: boolean }
  >;
  overridesPayload: () => Array<Record<string, unknown>>;
  onInvalidate: () => void;
};

/** @deprecated Prefer {@link DsiResolutionPlanToolbar} + {@link DsiRegionChannelTabPanel} on the Region & channel tab. */
export function DsiResolutionSuggestionsBar(plan: PlanHookSlice) {
  return <DsiResolutionPlanToolbar {...plan} />;
}

/** @deprecated Geo stewardship lives on the Region & channel tab — use {@link DsiRegionChannelTabPanel}. */
export function DsiUnresolvedGeoStewardBlock(plan: PlanHookSlice) {
  return (
    <DsiRegionChannelTabPanel
      importJobId={plan.importJobId}
      unresolvedGeoQuery={plan.unresolvedGeoQuery}
      catalogChannels={plan.channels}
      catalogRegions={plan.regions}
      onInvalidate={plan.onInvalidate}
    />
  );
}

/** @deprecated */
export function DsiResolutionPlanAdvancedAccordion(plan: PlanHookSlice) {
  return (
    <>
      <DsiResolutionPlanToolbar {...plan} />
      <DsiRegionChannelTabPanel
        importJobId={plan.importJobId}
        unresolvedGeoQuery={plan.unresolvedGeoQuery}
        catalogChannels={plan.channels}
        catalogRegions={plan.regions}
        onInvalidate={plan.onInvalidate}
      />
    </>
  );
}
