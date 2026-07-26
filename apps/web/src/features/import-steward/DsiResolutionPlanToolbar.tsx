'use client';

import { DSI_ENGINE_CONFIG } from './dsiSteward.engineConfig';
import {
  StewardResolutionPlanToolbar,
  type StewardResolutionPlanToolbarDsiExtras,
  type StewardResolutionPlanToolbarSlice,
} from './StewardResolutionPlanToolbar';

type DsiToolbarPlan = StewardResolutionPlanToolbarSlice & StewardResolutionPlanToolbarDsiExtras;

/** @deprecated Prefer {@link StewardResolutionPlanToolbar} with engine testIds + dsiExtras. */
export function DsiResolutionPlanToolbar(plan: DsiToolbarPlan) {
  const {
    candidatesCount,
    suggestionsQuery,
    resolutionPlan,
    planGlobalSuspicious,
    setPlanGlobalSuspicious,
    planLoadToken,
    planTableRows,
    refreshPlanEffective,
    overridesPayload,
  } = plan;
  return (
    <StewardResolutionPlanToolbar
      plan={{ candidatesCount, suggestionsQuery }}
      testIds={DSI_ENGINE_CONFIG.planToolbarTestIds}
      dsiExtras={{
        resolutionPlan,
        planGlobalSuspicious,
        setPlanGlobalSuspicious,
        planLoadToken,
        planTableRows,
        refreshPlanEffective,
        overridesPayload,
      }}
    />
  );
}
