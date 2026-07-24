'use client';

import { DSI_ENGINE_CONFIG } from './dsiSteward.engineConfig';
import { StewardResolutionPlanToolbar } from './StewardResolutionPlanToolbar';
import type { StewardResolutionPlanToolbarSlice } from './StewardResolutionPlanToolbar';

/** @deprecated Prefer {@link StewardResolutionPlanToolbar} with engine testIds. */
export function DsiResolutionPlanToolbar(plan: StewardResolutionPlanToolbarSlice) {
  return <StewardResolutionPlanToolbar plan={plan} testIds={DSI_ENGINE_CONFIG.planToolbarTestIds} />;
}
